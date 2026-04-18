from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .dataset import load_dataset_auto
from .schemas import SEPSIS_ACTIONS, Checkpoint, Trajectory
from .tools import ToolRuntime, build_tool_runtime


DEFAULT_DATASET_PATH = Path(__file__).resolve().parents[2] / "rolling_monitor_dataset" / "sepsis" / "rolling_sepsis.csv"
DEFAULT_GUIDELINE_DIR = Path(__file__).resolve().parents[2] / "clinical_guidelines"
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
DECISION_TOOL_ALIASES = ("query_infection", "query_sofa_by_hour")
INVESTIGATION_TOOL_ALIASES = DECISION_TOOL_ALIASES + ("query_aki_by_hour",)
MAX_AGENT_ROUNDS = 8

TOOL_ALIAS_CONFIG: dict[str, dict[str, Any]] = {
    "query_infection": {
        "runtime_name": "query_suspicion_of_infection",
        "label": "query_infection",
        "description": "Return infection suspicion evidence visible by the current checkpoint.",
    },
    "query_sofa_by_hour": {
        "runtime_name": "query_sofa",
        "label": "query_sofa_by_hour",
        "description": "Return the latest and maximum visible SOFA evidence by the current checkpoint.",
    },
    "query_aki_by_hour": {
        "runtime_name": "query_kdigo_stage",
        "label": "query_aki_by_hour",
        "description": "Return visible AKI / KDIGO evidence by the current checkpoint.",
    },
}


@dataclass(slots=True)
class GuidelineDocument:
    path: str
    title: str
    content: str


@dataclass(slots=True)
class DemoBackend:
    dataset_path: str
    db_path: str
    guideline_dir: str
    runtime: ToolRuntime
    trajectories_by_stay: dict[int, Trajectory]
    guideline_documents: list[GuidelineDocument]

    @property
    def guideline_markdown(self) -> str:
        if not self.guideline_documents:
            return "No guideline files found."
        sections = []
        for document in self.guideline_documents:
            sections.append(f"## {document.title}\n\n```text\n{document.content.strip()}\n```")
        return "\n\n".join(sections)

    @property
    def sepsis_guidance_text(self) -> str:
        if not self.guideline_documents:
            return "No sepsis guideline summary loaded."
        preferred = [
            document
            for document in self.guideline_documents
            if "sepsis" in document.title.lower()
        ]
        target_docs = preferred or self.guideline_documents
        return "\n\n".join(f"{document.title}\n{document.content.strip()}" for document in target_docs)

    @property
    def investigation_guidance_text(self) -> str:
        if not self.guideline_documents:
            return "No guideline summary loaded."
        return "\n\n".join(f"{document.title}\n{document.content.strip()}" for document in self.guideline_documents)

    @property
    def available_stay_ids(self) -> list[int]:
        return sorted(self.trajectories_by_stay)


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL | re.IGNORECASE).strip()
    decoder = json.JSONDecoder()
    try:
        payload = json.loads(cleaned)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    for match in re.finditer(r"\{", cleaned):
        try:
            payload, _ = decoder.raw_decode(cleaned[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError(f"Expected JSON object, received: {cleaned}")


def _chat_message_text(message: Any) -> str:
    content = getattr(message, "content", "") or ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
            elif hasattr(item, "text"):
                parts.append(str(getattr(item, "text", "")))
        return "\n".join(part for part in parts if part).strip()
    return str(content).strip()


def _assistant_message_to_dict(message: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "role": "assistant",
        "content": _chat_message_text(message),
    }
    tool_calls = getattr(message, "tool_calls", None) or []
    if tool_calls:
        payload["tool_calls"] = [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                },
            }
            for tool_call in tool_calls
        ]
    return payload


def _load_guideline_documents(guideline_dir: str | Path) -> list[GuidelineDocument]:
    root = Path(guideline_dir)
    if not root.exists():
        return []
    documents: list[GuidelineDocument] = []
    for path in sorted(root.glob("*")):
        if not path.is_file():
            continue
        documents.append(
            GuidelineDocument(
                path=str(path),
                title=path.stem.replace("_", " ").title(),
                content=path.read_text().strip(),
            )
        )
    return documents


def _trajectory_patient_summary(trajectory: Trajectory) -> dict[str, Any]:
    return {
        "trajectory_id": trajectory.trajectory_id,
        "stay_id": trajectory.stay_id,
        "subject_id": trajectory.subject_id,
        "hadm_id": trajectory.hadm_id,
        "icu_intime": trajectory.icu_intime,
        "icu_outtime": trajectory.icu_outtime,
        "icu_los_hours": trajectory.icu_los_hours,
        "reference_transitions": trajectory.transitions,
    }


def _ensure_openai_client(api_key: str | None):
    if not (api_key or os.environ.get("OPENAI_API_KEY")):
        raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY or enter it in the UI.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("The demo requires the 'openai' package to be installed.") from exc
    return OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))


def _tool_specs(tool_names: tuple[str, ...]) -> list[dict[str, Any]]:
    specs = []
    for tool_name in tool_names:
        config = TOOL_ALIAS_CONFIG[tool_name]
        specs.append(
            {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": config["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "stay_id": {
                                "type": "integer",
                                "description": "ICU stay identifier. The app will pin this to the active stay.",
                            },
                            "t_hour": {
                                "type": "integer",
                                "description": "Current checkpoint hour. The app will pin this to the active checkpoint.",
                            },
                        },
                        "required": ["stay_id", "t_hour"],
                    },
                },
            }
        )
    return specs


def _format_infection_summary(payload: dict[str, Any]) -> str:
    if not payload:
        return "No infection query result yet."
    if not payload.get("has_suspected_infection"):
        return "No suspected infection is visible by this checkpoint."
    first_hour = payload.get("first_visible_suspected_infection_hour")
    evidence = payload.get("evidence") or []
    return (
        f"Suspected infection is visible. First visible infection hour: {first_hour}. "
        f"Visible evidence rows: {len(evidence)}."
    )


def _format_sofa_summary(payload: dict[str, Any]) -> str:
    if not payload:
        return "No SOFA query result yet."
    latest_sofa = payload.get("latest_sofa_24hours")
    latest_hr = payload.get("latest_visible_hr")
    max_sofa = payload.get("max_sofa_24hours_so_far")
    if latest_sofa is None:
        return "No visible SOFA row is available by this checkpoint."
    return f"Latest visible SOFA is {latest_sofa} at hr {latest_hr}; max SOFA so far is {max_sofa}."


def _format_aki_summary(payload: dict[str, Any]) -> str:
    if not payload:
        return "No AKI query result yet."
    stage = payload.get("latest_aki_stage_smoothed")
    label = payload.get("current_aki_state_label")
    if stage is None:
        return "No visible AKI / KDIGO row is available by this checkpoint."
    return f"Latest visible AKI stage is {stage} ({label})."


def _build_structured_rationale(action: str, tool_outputs: dict[str, dict[str, Any]], decision_note: str) -> dict[str, Any]:
    infection = tool_outputs.get("query_infection", {})
    sofa = tool_outputs.get("query_sofa_by_hour", {})
    aki = tool_outputs.get("query_aki_by_hour", {})

    infection_visible = bool(infection.get("has_suspected_infection"))
    latest_sofa = sofa.get("latest_sofa_24hours")
    aki_stage = aki.get("latest_aki_stage_smoothed")

    supporting: list[str] = []
    missing: list[str] = []
    next_checks: list[str] = []

    if infection_visible:
        supporting.append(_format_infection_summary(infection))
    else:
        missing.append("No antibiotic-plus-culture pattern has become visible yet.")
        next_checks.append("Re-check infection evidence at the next checkpoint.")

    if latest_sofa is None:
        missing.append("No visible SOFA row is available yet.")
        next_checks.append("Re-check organ dysfunction evidence with the next visible SOFA update.")
    else:
        supporting.append(_format_sofa_summary(sofa))
        if latest_sofa < 2:
            next_checks.append("Watch for a visible SOFA rise to 2 or greater before triggering a sepsis alert.")

    if aki_stage is not None:
        supporting.append(_format_aki_summary(aki))

    if action == "keep_monitoring":
        why_not_keep = "Visible evidence remains below the threshold for leaving the baseline monitoring state."
        why_not_suspect = (
            "Infection suspicion is not yet established in the visible evidence."
            if not infection_visible
            else "The model still chose to hold baseline monitoring despite some infection evidence."
        )
        why_not_alert = (
            "A sepsis alert needs both infection evidence and alert-level organ dysfunction, which are not both clearly visible yet."
        )
    elif action == "infection_suspect":
        why_not_keep = "The monitoring state changed because suspected infection is already visible."
        why_not_suspect = "This is the selected intermediate surveillance state."
        why_not_alert = (
            "Alert-level organ dysfunction is not yet clearly visible."
            if latest_sofa is None or latest_sofa < 2
            else "The model did not fully commit to alerting despite visible dysfunction."
        )
    else:
        why_not_keep = "Baseline monitoring is no longer appropriate because sepsis-level concern is visible."
        why_not_suspect = "The model escalated past intermediate suspicion because it judged alert-level evidence to be present."
        why_not_alert = "This is the selected escalation state."

    if not next_checks:
        next_checks.append("Continue monitoring the next scheduled checkpoint for trend progression.")

    organ_status = (
        "No visible SOFA row yet."
        if latest_sofa is None
        else f"Latest visible SOFA is {latest_sofa}."
    )
    if latest_sofa is not None and latest_sofa >= 2:
        organ_status += " This meets alert-level organ dysfunction evidence."
    elif latest_sofa is not None:
        organ_status += " This does not yet meet the alert threshold of SOFA >= 2."

    return {
        "infection_status": _format_infection_summary(infection),
        "organ_dysfunction_status": organ_status,
        "key_supporting_evidence": supporting or ["No positive supporting evidence has been established yet."],
        "key_missing_evidence": missing or ["No major missing-evidence warning at this checkpoint."],
        "why_not_keep_monitoring": why_not_keep,
        "why_not_infection_suspect": why_not_suspect,
        "why_not_trigger_sepsis_alert": why_not_alert,
        "recommended_next_checks": next_checks,
        "decision_note": decision_note.strip() or "No additional decision note returned by the model.",
    }


def _decision_system_prompt(guidance_text: str) -> str:
    valid_actions = ", ".join(SEPSIS_ACTIONS)
    return (
        "You are an ICU sepsis surveillance agent operating on a rolling checkpoint demo.\n"
        "Your job is to monitor one ICU stay at a time under partial observability.\n"
        "At each checkpoint, review only evidence visible by the current time.\n"
        "You must call both query_infection and query_sofa_by_hour before you finalize.\n"
        "Do not mention future checkpoints.\n"
        "Return JSON only when you finalize.\n"
        f"Valid actions: {valid_actions}.\n"
        'Final JSON format: {"action":"infection_suspect","decision_note":"one or two short sentences"}\n\n'
        "Guideline summary:\n"
        f"{guidance_text}"
    )


def _decision_user_payload(session: dict[str, Any], checkpoint: dict[str, Any]) -> dict[str, Any]:
    completed_steps = session["completed_steps"]
    prior_actions = [
        {
            "step_index": step["step_index"],
            "t_hour": step["t_hour"],
            "action": step["action"],
        }
        for step in completed_steps
    ]
    return {
        "session_instruction": session["instruction"],
        "patient": session["patient_summary"],
        "current_checkpoint": {
            "step_index": session["next_step_index"],
            "t_hour": checkpoint["t_hour"],
            "checkpoint_time": checkpoint.get("checkpoint_time"),
            "reference_label": checkpoint.get("state_label"),
        },
        "prior_agent_actions": prior_actions,
        "required_tools": list(DECISION_TOOL_ALIASES),
    }


def _investigation_system_prompt(guidance_text: str) -> str:
    return (
        "You are helping a clinician inspect the current checkpoint in an ICU sepsis monitoring demo.\n"
        "You may call tools to investigate infection, SOFA, or AKI evidence visible by the current checkpoint.\n"
        "Stay grounded in visible evidence only.\n"
        "Do not silently change the official checkpoint action. If the user should re-evaluate, say so explicitly.\n"
        "Respond with concise markdown after any tool calls.\n\n"
        "Guideline summary:\n"
        f"{guidance_text}"
    )


def _execute_tool(
    backend: DemoBackend,
    tool_alias: str,
    stay_id: int,
    t_hour: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    config = TOOL_ALIAS_CONFIG[tool_alias]
    output = backend.runtime.execute(
        config["runtime_name"],
        {"stay_id": stay_id, "t_hour": t_hour},
    )
    event = {
        "tool_name": tool_alias,
        "runtime_tool_name": config["runtime_name"],
        "arguments": {"stay_id": stay_id, "t_hour": t_hour},
        "output": output,
    }
    return output, event


def _run_openai_tool_loop(
    *,
    client: Any,
    model: str,
    messages: list[dict[str, Any]],
    backend: DemoBackend,
    stay_id: int,
    t_hour: int,
    allowed_tools: tuple[str, ...],
    expect_json: bool,
    required_tool_set: set[str] | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, dict[str, Any]]]:
    tool_events: list[dict[str, Any]] = []
    tool_outputs: dict[str, dict[str, Any]] = {}
    required_tool_set = required_tool_set or set()

    for _ in range(MAX_AGENT_ROUNDS):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=_tool_specs(allowed_tools),
            tool_choice="auto",
            temperature=0.0,
            max_tokens=700,
        )
        message = response.choices[0].message
        messages.append(_assistant_message_to_dict(message))
        tool_calls = getattr(message, "tool_calls", None) or []
        if tool_calls:
            for tool_call in tool_calls:
                tool_alias = tool_call.function.name
                if tool_alias not in allowed_tools:
                    continue
                output, event = _execute_tool(backend, tool_alias, stay_id=stay_id, t_hour=t_hour)
                tool_events.append(event)
                tool_outputs[tool_alias] = output
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(output),
                    }
                )
            continue

        content = _chat_message_text(message)
        if expect_json and not required_tool_set.issubset(tool_outputs):
            missing = sorted(required_tool_set - set(tool_outputs))
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "You must call all required tools before deciding. "
                        f"Missing tools: {', '.join(missing)}. "
                        'Then return JSON only as {"action":"...","decision_note":"..."}'
                    ),
                }
            )
            continue
        return content, tool_events, tool_outputs

    raise RuntimeError("OpenAI tool loop exceeded the maximum number of rounds.")


def _run_decision_step(session: dict[str, Any], backend: DemoBackend, api_key: str, model: str) -> dict[str, Any]:
    checkpoint = session["checkpoints"][session["next_step_index"]]
    client = _ensure_openai_client(api_key)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _decision_system_prompt(backend.sepsis_guidance_text)},
        {
            "role": "user",
            "content": json.dumps(_decision_user_payload(session, checkpoint), indent=2),
        },
    ]
    content, tool_events, tool_outputs = _run_openai_tool_loop(
        client=client,
        model=model,
        messages=messages,
        backend=backend,
        stay_id=session["stay_id"],
        t_hour=checkpoint["t_hour"],
        allowed_tools=DECISION_TOOL_ALIASES,
        expect_json=True,
        required_tool_set=set(DECISION_TOOL_ALIASES),
    )
    payload = _extract_json_object(content)
    action = payload.get("action")
    if action not in SEPSIS_ACTIONS:
        raise ValueError(f"Invalid action returned by model: {action}")
    decision_note = str(payload.get("decision_note", "")).strip()
    rationale = _build_structured_rationale(action, tool_outputs, decision_note)
    step_result = {
        "step_index": session["next_step_index"],
        "t_hour": checkpoint["t_hour"],
        "checkpoint_time": checkpoint.get("checkpoint_time"),
        "reference_action": checkpoint.get("state_label"),
        "action": action,
        "decision_note": decision_note,
        "rationale": rationale,
        "decision_tool_events": tool_events,
        "decision_tool_outputs": tool_outputs,
        "investigation_turns": [],
    }
    return step_result


def _run_follow_up(
    session: dict[str, Any],
    backend: DemoBackend,
    api_key: str,
    model: str,
    question: str,
) -> tuple[str, list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if not session["completed_steps"]:
        raise ValueError("Run at least one checkpoint before asking follow-up questions.")
    current_step = session["completed_steps"][-1]
    checkpoint_payload = {
        "patient": session["patient_summary"],
        "current_checkpoint": {
            "step_index": current_step["step_index"],
            "t_hour": current_step["t_hour"],
            "checkpoint_time": current_step.get("checkpoint_time"),
            "official_action": current_step["action"],
            "decision_note": current_step.get("decision_note"),
            "rationale": current_step["rationale"],
            "decision_tool_outputs": current_step["decision_tool_outputs"],
        },
    }
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _investigation_system_prompt(backend.investigation_guidance_text)},
        {"role": "user", "content": json.dumps(checkpoint_payload, indent=2)},
    ]
    for turn in current_step["investigation_turns"]:
        messages.append({"role": "user", "content": turn["question"]})
        messages.append({"role": "assistant", "content": turn["answer"]})
    messages.append({"role": "user", "content": question})
    client = _ensure_openai_client(api_key)
    answer, tool_events, tool_outputs = _run_openai_tool_loop(
        client=client,
        model=model,
        messages=messages,
        backend=backend,
        stay_id=session["stay_id"],
        t_hour=current_step["t_hour"],
        allowed_tools=INVESTIGATION_TOOL_ALIASES,
        expect_json=False,
    )
    return answer.strip() or "No answer returned.", tool_events, tool_outputs


def _serialize_checkpoints(trajectory: Trajectory) -> list[dict[str, Any]]:
    checkpoints: list[dict[str, Any]] = []
    for checkpoint in trajectory.checkpoints:
        checkpoints.append(
            {
                "t_hour": checkpoint.t_hour,
                "checkpoint_time": checkpoint.checkpoint_time,
                "state_label": checkpoint.state_label,
                "terminal": checkpoint.terminal,
            }
        )
    return checkpoints


@lru_cache(maxsize=8)
def load_demo_backend(dataset_path: str, db_path: str, guideline_dir: str) -> DemoBackend:
    if not db_path:
        raise ValueError("A DuckDB path is required for the demo because tool outputs come from official derived SQL wrappers.")
    trajectories = [
        trajectory
        for trajectory in load_dataset_auto(dataset_path)
        if not trajectory.is_multitask() and trajectory.primary_task_name() == "sepsis"
    ]
    trajectories_by_stay = {trajectory.stay_id: trajectory for trajectory in trajectories}
    if not trajectories_by_stay:
        raise ValueError("No single-task sepsis trajectories were found in the selected dataset.")
    runtime = build_tool_runtime(tool_backend="official", db_path=db_path or None, concepts=None)
    return DemoBackend(
        dataset_path=dataset_path,
        db_path=db_path,
        guideline_dir=guideline_dir,
        runtime=runtime,
        trajectories_by_stay=trajectories_by_stay,
        guideline_documents=_load_guideline_documents(guideline_dir),
    )


def _empty_session_view(status_message: str, guideline_markdown: str) -> tuple[Any, ...]:
    return (
        None,
        status_message,
        "No patient loaded.",
        "No checkpoint loaded.",
        "No action yet.",
        "No rationale yet.",
        "No cumulative evidence yet.",
        {},
        [],
        [],
        guideline_markdown,
        {},
    )


def _timeline_rows(session: dict[str, Any]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for step in session["completed_steps"]:
        rows.append(
            [
                step["step_index"],
                step["t_hour"],
                step.get("checkpoint_time"),
                step.get("reference_action"),
                step["action"],
                ", ".join(event["tool_name"] for event in step["decision_tool_events"]),
            ]
        )
    return rows


def _cumulative_evidence_markdown(session: dict[str, Any]) -> str:
    if not session["completed_steps"]:
        return "No checkpoints completed yet."
    action_lines = []
    for step in session["completed_steps"]:
        action_lines.append(f"- t={step['t_hour']}: {step['action']}")
    latest = session["completed_steps"][-1]
    infection_summary = latest["rationale"]["infection_status"]
    organ_summary = latest["rationale"]["organ_dysfunction_status"]
    return (
        f"Completed checkpoints: {len(session['completed_steps'])} / {len(session['checkpoints'])}\n\n"
        "Action trace:\n"
        + "\n".join(action_lines)
        + "\n\nLatest visible evidence:\n"
        f"- {infection_summary}\n"
        f"- {organ_summary}"
    )


def _patient_markdown(session: dict[str, Any]) -> str:
    patient = session["patient_summary"]
    return (
        f"### Patient Context\n"
        f"- Stay ID: {patient['stay_id']}\n"
        f"- Subject ID: {patient['subject_id']}\n"
        f"- HADM ID: {patient['hadm_id']}\n"
        f"- ICU In: {patient['icu_intime']}\n"
        f"- ICU Out: {patient['icu_outtime']}\n"
        f"- ICU LOS Hours: {patient['icu_los_hours']}\n"
        f"- Trajectory ID: {patient['trajectory_id']}"
    )


def _checkpoint_markdown(session: dict[str, Any]) -> str:
    if session["completed_steps"]:
        latest = session["completed_steps"][-1]
        return (
            "### Current Checkpoint\n"
            f"- Step Index: {latest['step_index']}\n"
            f"- t_hour: {latest['t_hour']}\n"
            f"- checkpoint_time: {latest.get('checkpoint_time')}\n"
            f"- reference label: {latest.get('reference_action')}"
        )
    next_index = session["next_step_index"]
    if next_index >= len(session["checkpoints"]):
        return "### Current Checkpoint\nAll checkpoints completed."
    checkpoint = session["checkpoints"][next_index]
    return (
        "### Current Checkpoint\n"
        f"- Next step index: {next_index}\n"
        f"- Upcoming t_hour: {checkpoint['t_hour']}\n"
        f"- checkpoint_time: {checkpoint.get('checkpoint_time')}\n"
        f"- reference label: {checkpoint.get('state_label')}"
    )


def _action_markdown(session: dict[str, Any]) -> str:
    if not session["completed_steps"]:
        return "### Action\nNo action yet."
    latest = session["completed_steps"][-1]
    return (
        "### Action\n"
        f"- Agent action: `{latest['action']}`\n"
        f"- Model note: {latest.get('decision_note') or 'No short note returned.'}"
    )


def _rationale_markdown(session: dict[str, Any]) -> str:
    if not session["completed_steps"]:
        return "### Structured Rationale\nNo rationale yet."
    rationale = session["completed_steps"][-1]["rationale"]
    return (
        "### Structured Rationale\n"
        f"- Infection status: {rationale['infection_status']}\n"
        f"- Organ dysfunction status: {rationale['organ_dysfunction_status']}\n"
        + "\nSupporting evidence:\n"
        + "\n".join(f"- {item}" for item in rationale["key_supporting_evidence"])
        + "\n\nMissing evidence / caution:\n"
        + "\n".join(f"- {item}" for item in rationale["key_missing_evidence"])
        + "\n\nDecision boundaries:\n"
        + f"- Why not keep_monitoring: {rationale['why_not_keep_monitoring']}\n"
        + f"- Why not infection_suspect: {rationale['why_not_infection_suspect']}\n"
        + f"- Why not trigger_sepsis_alert: {rationale['why_not_trigger_sepsis_alert']}\n"
        + "\n\nRecommended next checks:\n"
        + "\n".join(f"- {item}" for item in rationale["recommended_next_checks"])
    )


def _current_tools_payload(session: dict[str, Any]) -> dict[str, Any]:
    if not session["completed_steps"]:
        return {}
    latest = session["completed_steps"][-1]
    payload: dict[str, Any] = {
        "decision_tools": latest["decision_tool_events"],
    }
    if latest["investigation_turns"]:
        payload["latest_investigation"] = latest["investigation_turns"][-1]
    return payload


def _chatbot_messages(session: dict[str, Any]) -> list[dict[str, str]]:
    if not session["completed_steps"]:
        return []
    messages: list[dict[str, str]] = []
    for step in session["completed_steps"]:
        for turn in step["investigation_turns"]:
            messages.append({"role": "user", "content": turn["question"]})
            messages.append({"role": "assistant", "content": turn["answer"]})
    return messages


def _session_json(session: dict[str, Any] | None) -> dict[str, Any]:
    return session or {}


def _render_session(session: dict[str, Any], backend: DemoBackend, status_message: str) -> tuple[Any, ...]:
    return (
        session,
        status_message,
        _patient_markdown(session),
        _checkpoint_markdown(session),
        _action_markdown(session),
        _rationale_markdown(session),
        _cumulative_evidence_markdown(session),
        _current_tools_payload(session),
        _timeline_rows(session),
        _chatbot_messages(session),
        backend.guideline_markdown,
        _session_json(session),
    )


def start_session(
    dataset_path: str,
    db_path: str,
    guideline_dir: str,
    stay_id: str,
    instruction: str,
):
    try:
        backend = load_demo_backend(dataset_path, db_path, guideline_dir)
        selected_stay_id = int(str(stay_id).strip())
        trajectory = backend.trajectories_by_stay.get(selected_stay_id)
        if trajectory is None:
            available_preview = ", ".join(str(value) for value in backend.available_stay_ids[:10])
            raise ValueError(f"stay_id {selected_stay_id} was not found. Example stay_ids: {available_preview}")
        session = {
            "dataset_path": dataset_path,
            "db_path": db_path,
            "guideline_dir": guideline_dir,
            "stay_id": selected_stay_id,
            "instruction": instruction.strip(),
            "patient_summary": _trajectory_patient_summary(trajectory),
            "checkpoints": _serialize_checkpoints(trajectory),
            "completed_steps": [],
            "next_step_index": 0,
        }
        return _render_session(
            session,
            backend,
            f"Session initialized for stay_id {selected_stay_id}. Run the first checkpoint when ready.",
        )
    except Exception as exc:
        guideline_markdown = _load_guideline_documents(guideline_dir)
        combined = "\n\n".join(doc.content for doc in guideline_markdown) if guideline_markdown else "No guideline files found."
        return _empty_session_view(f"Failed to start session: {exc}", combined)


def run_next_checkpoint(session: dict[str, Any] | None, api_key: str, model: str):
    if not session:
        return _empty_session_view("Start a session first.", "No guideline files loaded.")
    try:
        backend = load_demo_backend(session["dataset_path"], session["db_path"], session["guideline_dir"])
        if session["next_step_index"] >= len(session["checkpoints"]):
            return _render_session(session, backend, "All checkpoints are already complete.")
        step_result = _run_decision_step(session, backend, api_key=api_key, model=model or DEFAULT_MODEL)
        session["completed_steps"].append(step_result)
        session["next_step_index"] += 1
        status_message = (
            f"Completed checkpoint t={step_result['t_hour']} with action {step_result['action']}."
        )
        if session["next_step_index"] >= len(session["checkpoints"]):
            status_message += " Monitoring session is complete."
        return _render_session(session, backend, status_message)
    except Exception as exc:
        backend = load_demo_backend(session["dataset_path"], session["db_path"], session["guideline_dir"])
        return _render_session(session, backend, f"Checkpoint run failed: {exc}")


def run_all_checkpoints(session: dict[str, Any] | None, api_key: str, model: str):
    if not session:
        return _empty_session_view("Start a session first.", "No guideline files loaded.")
    try:
        backend = load_demo_backend(session["dataset_path"], session["db_path"], session["guideline_dir"])
        completed_now = 0
        while session["next_step_index"] < len(session["checkpoints"]):
            step_result = _run_decision_step(session, backend, api_key=api_key, model=model or DEFAULT_MODEL)
            session["completed_steps"].append(step_result)
            session["next_step_index"] += 1
            completed_now += 1
        return _render_session(
            session,
            backend,
            f"Completed {completed_now} checkpoint(s). Monitoring session is complete.",
        )
    except Exception as exc:
        backend = load_demo_backend(session["dataset_path"], session["db_path"], session["guideline_dir"])
        return _render_session(session, backend, f"Run-to-end failed: {exc}")


def ask_follow_up_question(session: dict[str, Any] | None, api_key: str, model: str, question: str):
    if not session:
        return _empty_session_view("Start a session first.", "No guideline files loaded.")
    try:
        backend = load_demo_backend(session["dataset_path"], session["db_path"], session["guideline_dir"])
        if not question.strip():
            return _render_session(session, backend, "Enter a follow-up question first.")
        answer, tool_events, tool_outputs = _run_follow_up(
            session,
            backend,
            api_key=api_key,
            model=model or DEFAULT_MODEL,
            question=question.strip(),
        )
        session["completed_steps"][-1]["investigation_turns"].append(
            {
                "question": question.strip(),
                "answer": answer,
                "tool_events": tool_events,
                "tool_outputs": tool_outputs,
            }
        )
        return _render_session(
            session,
            backend,
            f"Added investigation response for t={session['completed_steps'][-1]['t_hour']}.",
        )
    except Exception as exc:
        backend = load_demo_backend(session["dataset_path"], session["db_path"], session["guideline_dir"])
        return _render_session(session, backend, f"Follow-up failed: {exc}")


def reset_session():
    docs = _load_guideline_documents(DEFAULT_GUIDELINE_DIR)
    combined = (
        "\n\n".join(f"## {doc.title}\n\n```text\n{doc.content}\n```" for doc in docs)
        if docs
        else "No guideline files loaded."
    )
    return _empty_session_view("Session cleared.", combined)


def build_demo(
    *,
    default_dataset_path: str = str(DEFAULT_DATASET_PATH),
    default_db_path: str = "",
    default_guideline_dir: str = str(DEFAULT_GUIDELINE_DIR),
):
    try:
        import gradio as gr
    except ImportError as exc:
        raise RuntimeError("Launching the demo requires the 'gradio' package to be installed.") from exc

    css = """
    .status-panel {border: 1px solid #d6e4ff; border-radius: 12px; padding: 12px; background: linear-gradient(180deg, #f8fbff 0%, #eef5ff 100%);}
    .console-title {font-size: 1.25rem; font-weight: 700; letter-spacing: 0.02em;}
    """

    with gr.Blocks(title="Rolling ICU Monitoring Console") as demo:
        gr.Markdown(
            """
            <div class="status-panel">
              <div class="console-title">Rolling ICU Monitoring Console</div>
              OpenAI-backed sepsis checkpoint monitoring with structured rationale and interactive follow-up investigation.
            </div>
            """
        )
        session_state = gr.State(value=None)

        with gr.Row():
            dataset_path = gr.Textbox(label="Dataset Path", value=default_dataset_path)
            db_path = gr.Textbox(label="DuckDB Path", value=default_db_path, placeholder="Path to mimic4_dk.db")
            guideline_dir = gr.Textbox(label="Guideline Directory", value=default_guideline_dir)

        with gr.Row():
            api_key = gr.Textbox(label="OpenAI API Key", type="password", placeholder="Optional if OPENAI_API_KEY is already set")
            model = gr.Textbox(label="OpenAI Model", value=DEFAULT_MODEL)

        with gr.Row():
            stay_id = gr.Textbox(label="Stay ID", placeholder="e.g. 30157290")
            instruction = gr.Textbox(
                label="Monitoring Instruction",
                lines=2,
                value="New ICU admission received. Monitor this patient for evolving sepsis risk. Review evidence over time and issue alerts when appropriate.",
            )

        with gr.Row():
            start_button = gr.Button("Start Session", variant="primary")
            next_button = gr.Button("Run Next Checkpoint")
            run_all_button = gr.Button("Run To End")
            reset_button = gr.Button("Reset")

        status_markdown = gr.Markdown("No patient loaded yet.")

        with gr.Row():
            patient_markdown = gr.Markdown("No patient loaded.")
            checkpoint_markdown = gr.Markdown("No checkpoint loaded.")

        with gr.Row():
            action_markdown = gr.Markdown("No action yet.")
            rationale_markdown = gr.Markdown("No rationale yet.")

        with gr.Row():
            cumulative_markdown = gr.Markdown("No cumulative evidence yet.")
            current_tools = gr.JSON(label="Current Step Tool Activity", value={})

        timeline = gr.Dataframe(
            headers=["step_index", "t_hour", "checkpoint_time", "reference_action", "agent_action", "tools_called"],
            value=[],
            interactive=False,
            label="Checkpoint Timeline",
        )

        chatbot = gr.Chatbot(label="Follow-up Investigation", value=[])
        followup_question = gr.Textbox(
            label="Ask about the current checkpoint",
            placeholder="Why did you choose infection_suspect here?",
        )
        ask_button = gr.Button("Ask Follow-up")

        with gr.Accordion("Guidelines and Raw Session State", open=False):
            guideline_markdown = gr.Markdown("No guideline files loaded.")
            raw_session = gr.JSON(label="Session JSON", value={})

        outputs = [
            session_state,
            status_markdown,
            patient_markdown,
            checkpoint_markdown,
            action_markdown,
            rationale_markdown,
            cumulative_markdown,
            current_tools,
            timeline,
            chatbot,
            guideline_markdown,
            raw_session,
        ]

        start_button.click(
            start_session,
            inputs=[dataset_path, db_path, guideline_dir, stay_id, instruction],
            outputs=outputs,
        )
        next_button.click(
            run_next_checkpoint,
            inputs=[session_state, api_key, model],
            outputs=outputs,
        )
        run_all_button.click(
            run_all_checkpoints,
            inputs=[session_state, api_key, model],
            outputs=outputs,
        )
        ask_button.click(
            ask_follow_up_question,
            inputs=[session_state, api_key, model, followup_question],
            outputs=outputs,
        ).then(lambda: "", inputs=[], outputs=followup_question)
        reset_button.click(reset_session, inputs=[], outputs=outputs)

    demo.demo_css = css
    return demo


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch the rolling ICU Gradio monitoring demo.")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET_PATH), help="Path to the rolling sepsis dataset.")
    parser.add_argument("--db-path", default="", help="Path to the DuckDB database containing mimiciv_derived views.")
    parser.add_argument("--guideline-dir", default=str(DEFAULT_GUIDELINE_DIR), help="Path to the guideline directory.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--share", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    demo = build_demo(
        default_dataset_path=args.dataset,
        default_db_path=args.db_path,
        default_guideline_dir=args.guideline_dir,
    )
    demo.launch(
        server_name=args.host,
        server_port=args.port,
        share=args.share,
        css=getattr(demo, "demo_css", None),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
