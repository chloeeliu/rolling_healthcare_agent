from __future__ import annotations

import json
import os
from pathlib import Path
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .schemas import (
    ACTIONS,
    CODE_EXEC_TOOL_NAME,
    SEPSIS_TOOLBOX_TOOL_NAMES,
    SQL_EXEC_TOOL_NAME,
    TASK_BASELINE_ACTION,
    TASK_LABEL_SPACES,
    TASK_TOOL_NAMES,
    ActionDecision,
    ToolCall,
)


class Agent(Protocol):
    def next_response(
        self,
        step_input: dict[str, Any],
        history: list[dict[str, Any]],
        available_tools: list[str],
    ) -> ToolCall | ActionDecision:
        ...


def _is_multitask_step(step_input: dict[str, Any]) -> bool:
    task_names = step_input.get("task_names") or []
    return len(task_names) > 1


TOOL_DESCRIPTIONS = {
    "query_suspicion_of_infection": "infection evidence visible by this checkpoint",
    "query_sofa": "current visible SOFA summary up to this checkpoint",
    "query_kdigo_stage": (
        "current visible AKI stage summary up to this checkpoint; for non-monotonic AKI, "
        "use current_aki_state_label as the primary decision field"
    ),
    "query_ventilation_status": "current and highest visible respiratory support up to this checkpoint",
}

ZEROSHOT_RAW_TABLES = [
    "mimiciv_icu.icustays",
    "mimiciv_icu.chartevents",
    "mimiciv_icu.inputevents",
    "mimiciv_icu.outputevents",
    "mimiciv_icu.d_items",
    "mimiciv_hosp.admissions",
    "mimiciv_hosp.labevents",
    "mimiciv_hosp.d_labitems",
    "mimiciv_hosp.microbiologyevents",
    "mimiciv_hosp.prescriptions",
]

ZEROSHOT_EXEC_TOOL_NAMES = {CODE_EXEC_TOOL_NAME, SQL_EXEC_TOOL_NAME}

CLINICAL_GUIDANCE = {
    "sepsis": [
        "If suspected infection is not visible yet, prefer keep_monitoring.",
        "If suspected infection is visible but alert-level organ dysfunction is not yet visible, prefer infection_suspect.",
        "If suspected infection is visible and SOFA is 2 or higher, this is usually alert-level evidence for trigger_sepsis_alert.",
        "Do not skip the intermediate infection_suspect state when infection is visible but sepsis alert evidence is not yet established.",
    ],
    "infection_only": [
        "If suspected infection is not visible yet, prefer keep_monitoring.",
        "If suspected infection is visible from the official antibiotic-culture overlap logic, prefer infection_suspect.",
        "Use the infection tool as the primary decision source; this task does not require SOFA reasoning.",
    ],
    "aki": [
        "If visible KDIGO stage is 0 or absent, prefer keep_monitoring.",
        "If visible KDIGO stage is 1, prefer suspect_aki.",
        "If visible KDIGO stage is 2 or 3, or stage-3/CRRT evidence is present, prefer trigger_aki_alert.",
    ],
    "respiratory_support": [
        "Map None and SupplementalOxygen to room_air_or_low_support.",
        "Map HFNC and non-invasive ventilation to high_flow_or_noninvasive_support.",
        "Map invasive ventilation and tracheostomy-level support to invasive_vent_required.",
        "If current support is unclear but highest support seen so far is higher, do not de-escalate below the highest visible support for this checkpoint.",
    ],
}

AKI_NON_MONOTONIC_GUIDANCE = [
    "Predict the current visible AKI state at this checkpoint rather than the first AKI onset.",
    "Use current_aki_state_label from query_kdigo_stage as the primary benchmark-facing state field.",
    "If current_aki_state_label is missing, then fall back to latest_aki_stage_smoothed.",
    "Do not assume AKI states are permanent. If the visible stage decreases, de-escalate to the current lower stage.",
    "Do not use latest_aki_stage when it conflicts with latest_aki_stage_smoothed.",
    "Use the latest visible KDIGO stage summary for the checkpoint, not the historical maximum alone.",
]


def _resolved_task_names(step_input: dict[str, Any]) -> list[str]:
    task_names = step_input.get("task_names") or []
    return task_names or ["sepsis"]


def _single_task_name(step_input: dict[str, Any]) -> str:
    return _resolved_task_names(step_input)[0]


def _is_toolbox_protocol(step_input: dict[str, Any]) -> bool:
    return step_input.get("protocol") == "rolling_toolbox_with_history"


def _required_tool_order(step_input: dict[str, Any], available_tools: list[str]) -> list[str]:
    ordered: list[str] = []
    for task_name in _resolved_task_names(step_input):
        for tool_name in TASK_TOOL_NAMES.get(task_name, []):
            if tool_name in available_tools and tool_name not in ordered:
                ordered.append(tool_name)
    return ordered


def _next_missing_tool(history: list[dict[str, Any]], available_tools: list[str]) -> str | None:
    return _next_missing_tool_for_step({}, history, available_tools)


def _next_missing_tool_for_step(
    step_input: dict[str, Any],
    history: list[dict[str, Any]],
    available_tools: list[str],
) -> str | None:
    seen_tools = [item["tool_name"] for item in history if item["type"] == "tool_call"]
    seen_set = set(seen_tools)
    for tool_name in _required_tool_order(step_input, available_tools):
        if tool_name in available_tools and tool_name not in seen_set:
            return tool_name
    return None


TASK_KEY_ALIASES = {
    "resp_support": "respiratory_support",
    "respiratory": "respiratory_support",
    "respiratory_status": "respiratory_support",
    "respiratory_support_status": "respiratory_support",
}


def _normalize_task_actions(task_actions: dict[str, Any]) -> dict[str, Any]:
    normalized = {}
    for key, value in task_actions.items():
        normalized[TASK_KEY_ALIASES.get(key, key)] = value
    return normalized


def _summarize_history(history: list[dict[str, Any]]) -> dict[str, Any]:
    tool_results = {}
    tool_calls = []
    for item in history:
        if item["type"] == "tool_call":
            tool_calls.append(item["tool_name"])
        elif item["type"] == "tool_output":
            tool_results[item["tool_name"]] = item["payload"]
    return {"tool_calls": tool_calls, "tool_results": tool_results}


def _clinical_guidance_text(task_names: list[str], step_input: dict[str, Any] | None = None) -> str:
    lines = ["Clinical guidance:"]
    for task_name in task_names:
        lines.append(f"- {task_name}:")
        for rule in _guidance_for_task(task_name, step_input):
            lines.append(f"  {rule}")
    return "\n".join(lines)


def _label_space_for_task(step_input: dict[str, Any], task_name: str) -> list[str]:
    return (step_input.get("label_spaces") or {}).get(task_name, TASK_LABEL_SPACES[task_name])


def _is_non_monotonic_aki_step(step_input: dict[str, Any], task_name: str) -> bool:
    label_space = _label_space_for_task(step_input, task_name)
    return task_name == "aki" and "aki_stage_1" in label_space


def _guidance_for_task(task_name: str, step_input: dict[str, Any] | None) -> list[str]:
    if task_name == "aki" and step_input is not None and _is_non_monotonic_aki_step(step_input, task_name):
        return AKI_NON_MONOTONIC_GUIDANCE
    return CLINICAL_GUIDANCE[task_name]


def _task_description(task_name: str, step_input: dict[str, Any]) -> str:
    return " | ".join(_label_space_for_task(step_input, task_name))


def _build_messages(
    step_input: dict[str, Any],
    history: list[dict[str, Any]],
    available_tools: list[str],
) -> list[dict[str, str]]:
    if _is_toolbox_protocol(step_input):
        return _build_toolbox_messages(step_input, history, available_tools)
    task_names = _resolved_task_names(step_input)
    next_tool = _next_missing_tool_for_step(step_input, history, available_tools)
    required_tool_order = _required_tool_order(step_input, available_tools)
    protocol = step_input.get("protocol", "rolling_no_history")
    rolling_history = step_input.get("rolling_history") or []
    if _is_multitask_step(step_input):
        seen_tools = {item["tool_name"] for item in history if item["type"] == "tool_call"}
        remaining_tools = [tool_name for tool_name in required_tool_order if tool_name not in seen_tools]
        executed = _summarize_history(history)
        stay_id = int(step_input["stay_id"])
        t_hour = int(step_input["t_hour"])
        system_prompt = (
            "You are an ICU rolling multi-task surveillance agent.\n"
            f"Monitored tasks: {', '.join(task_names)}.\n"
            f"Tool backend: {step_input.get('tool_backend', 'official')}.\n"
            "At each checkpoint, you may either call exactly one tool or return final task decisions.\n"
            "Use only the allowed tools and use them in the required order.\n"
            "Do not output reasoning, analysis, markdown, or <think> tags.\n"
            "Return exactly one JSON object and nothing else.\n\n"
            "Task semantics:\n"
        )
        for task_name in task_names:
            system_prompt += f"- {task_name}: {_task_description(task_name, step_input)}\n"
        system_prompt += "\nTool semantics:\n"
        for tool_name in required_tool_order:
            system_prompt += f"- {tool_name}: {TOOL_DESCRIPTIONS[tool_name]}\n"
        system_prompt += (
            "\n"
            + _clinical_guidance_text(task_names, step_input)
            + "\n"
            "\n"
            "\nRecommended decision pattern:\n"
            "1. Collect all required tool outputs for the current checkpoint.\n"
            "2. Use the visible evidence to assign one decision per task.\n"
            "3. Return one decision for every task in a fixed key order.\n\n"
            "Important:\n"
            "- Evidence may already be visible at t_hour=0 because some events can happen before ICU admission.\n"
            "- Do not assume keep_monitoring just because t_hour is small.\n"
            "- Do not omit any task.\n"
            "- The final JSON must contain exactly these keys in task_actions: "
            "sepsis, aki, respiratory_support.\n"
            f"- Before returning task_actions, collect all required tool outputs for this checkpoint: {required_tool_order}.\n"
            "- If any required tool is still missing, your next response must be a tool call for the first missing tool.\n"
            "- Never repeat a completed tool call.\n"
            "- Never guess a final decision before all required tool outputs are visible.\n\n"
            "Tool call format:\n"
            f'{{"tool_name":"query_kdigo_stage","arguments":{{"stay_id":{stay_id},"t_hour":{t_hour}}}}}\n\n'
            "Final decision format:\n"
            '{"task_actions":{"sepsis":"keep_monitoring","aki":"keep_monitoring","respiratory_support":"room_air_or_low_support"}}'
        )
        if protocol == "rolling_with_history":
            system_prompt += (
                "\n\nRolling-with-history protocol:\n"
                "- Prior checkpoint summaries for this stay may be provided in rolling_history.\n"
                "- Treat rolling_history as concise context from earlier checkpoints only.\n"
                "- You still must collect the required tools for the current checkpoint before making final decisions."
            )
        if next_tool is not None:
            system_prompt += f"\n\nCurrent requirement: the next response must be a tool call for `{next_tool}`."
        else:
            system_prompt += (
                "\n\nCurrent requirement: all required tool outputs are available, so the next response must be final task_actions."
            )
        user_payload = {
            "step_input": {
                "trajectory_id": step_input["trajectory_id"],
                "stay_id": stay_id,
                "step_index": step_input["step_index"],
                "t_hour": t_hour,
            },
            "task_mode": step_input.get("task_mode"),
            "tool_backend": step_input.get("tool_backend"),
            "available_tools": available_tools,
            "required_tool_order": remaining_tools,
            "already_called_tools": executed["tool_calls"],
            "tool_results_by_name": executed["tool_results"],
            "next_required_tool": next_tool,
            "protocol": protocol,
            "rolling_history": rolling_history,
        }
    else:
        stay_id = int(step_input["stay_id"])
        t_hour = int(step_input["t_hour"])
        task_name = task_names[0]
        label_space = _label_space_for_task(step_input, task_name)
        seen_tools = {item["tool_name"] for item in history if item["type"] == "tool_call"}
        remaining_tools = [tool_name for tool_name in required_tool_order if tool_name not in seen_tools]
        system_prompt = (
            f"You are an ICU rolling surveillance agent for task: {task_name}.\n"
            f"Tool backend: {step_input.get('tool_backend', 'official')}.\n"
            "Use only the allowed tools and use them in the required order.\n"
            "Do not output reasoning, analysis, markdown, or <think> tags.\n"
            "Return exactly one JSON object and nothing else.\n"
            "Evidence may already be visible at t_hour=0.\n\n"
            f"Task semantics: {_task_description(task_name, step_input)}\n\n"
            "Tool semantics:\n"
        )
        for tool_name in required_tool_order:
            system_prompt += f"- {tool_name}: {TOOL_DESCRIPTIONS[tool_name]}\n"
        system_prompt += (
            "\n"
            + _clinical_guidance_text([task_name], step_input)
            + "\n"
            "\n"
            "\nTool call format:\n"
            f'{{"tool_name":"{required_tool_order[0]}","arguments":{{"stay_id":{stay_id},"t_hour":{t_hour}}}}}\n\n'
            "Final action format:\n"
            '{"action":"keep_monitoring"}\n\n'
            "Valid final actions:\n"
        )
        for action in label_space:
            system_prompt += f"- {action}\n"
        if protocol == "rolling_with_history":
            system_prompt += (
                "\nRolling-with-history protocol:\n"
                "- Prior checkpoint summaries for this stay may be provided in rolling_history.\n"
                "- This is a real longitudinal monitoring task, so rolling_history can include every earlier checkpoint summary.\n"
                "- For sepsis, each rolling_history item may include step_index, t_hour, sofa_score, infection, and concise evidence.\n"
                "- Use rolling_history as context, but still call the required tools for the current checkpoint."
            )
        if next_tool is not None:
            system_prompt += f"\nCurrent requirement: the next response must be a tool call for `{next_tool}`."
        else:
            system_prompt += "\nCurrent requirement: all required tools are complete, so the next response must be a final action."
        user_payload = {
            "step_input": {
                "trajectory_id": step_input["trajectory_id"],
                "stay_id": stay_id,
                "step_index": step_input["step_index"],
                "t_hour": t_hour,
                "task_name": task_name,
            },
            "task_mode": step_input.get("task_mode"),
            "tool_backend": step_input.get("tool_backend"),
            "protocol": protocol,
            "rolling_history": rolling_history,
            "required_tool_order": remaining_tools,
            "history": history,
            "available_tools": available_tools,
        }
    user_prompt = json.dumps(user_payload, indent=2)
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _build_toolbox_messages(
    step_input: dict[str, Any],
    history: list[dict[str, Any]],
    available_tools: list[str],
) -> list[dict[str, str]]:
    task_name = _single_task_name(step_input)
    if _is_multitask_step(step_input) or task_name != "sepsis":
        raise ValueError("rolling_toolbox_with_history currently supports only the single-task sepsis task.")
    stay_id = int(step_input["stay_id"])
    t_hour = int(step_input["t_hour"])
    rolling_history = step_input.get("rolling_history") or []
    executed = _summarize_history(history)
    toolbox_tools = [tool_name for tool_name in SEPSIS_TOOLBOX_TOOL_NAMES if tool_name in available_tools]
    system_prompt = (
        "You are an ICU rolling surveillance agent for task: sepsis.\n"
        "Protocol: rolling_toolbox_with_history.\n"
        "This is a real longitudinal monitoring task for one stay across repeated checkpoints.\n"
        "rolling_history contains concise summaries from every earlier checkpoint for this same patient.\n"
        "At the current checkpoint, you may call zero or more tools, one per turn, and then return one final action.\n"
        "Use only tools that are clinically useful for the current checkpoint.\n"
        "Do not output reasoning, analysis, markdown, or <think> tags.\n"
        "Return exactly one JSON object and nothing else.\n"
        "Evidence may already be visible at t_hour=0 because hospital events can precede ICU admission.\n\n"
        f"Task semantics: {_task_description(task_name, step_input)}\n\n"
        "Available toolbox tools:\n"
    )
    for tool_name in toolbox_tools:
        system_prompt += f"- {tool_name}: {TOOL_DESCRIPTIONS[tool_name]}\n"
    system_prompt += (
        "\n"
        + _clinical_guidance_text([task_name], step_input)
        + "\n\n"
        "Tool-use guidance:\n"
        "- Use rolling_history to recognize what is already established longitudinally for this stay.\n"
        "- In rolling_history, null means not yet assessed at that checkpoint. Do not treat null as negative evidence.\n"
        "- Call only effective tools. Avoid low-value repeated calls when earlier checkpoints already establish the same fact.\n"
        "- query_suspicion_of_infection is high yield when infection status is still uncertain at the current checkpoint.\n"
        "- query_sofa is high yield when infection is visible or plausible and you need current organ-dysfunction evidence.\n"
        "- query_kdigo_stage and query_ventilation_status are optional contextual tools; they can support understanding severity but do not replace infection plus SOFA for the sepsis label.\n"
        "- If infection is already clearly established in rolling_history, repeated infection calls should be rare and should only happen when you need current-step confirmation.\n\n"
        "Evidence requirements:\n"
        "- Do not return infection_suspect unless suspected infection is explicitly supported by a current tool result or by an earlier positive rolling_history entry.\n"
        "- Do not return trigger_sepsis_alert unless suspected infection is explicitly supported and SOFA alert evidence is explicitly supported by a current tool result or by earlier rolling_history.\n"
        "- If no earlier checkpoint explicitly established infection, query_suspicion_of_infection before making a positive decision.\n"
        "- If no earlier checkpoint explicitly established SOFA alert evidence, query_sofa before making trigger_sepsis_alert.\n"
        "- Do not default to infection_suspect or trigger_sepsis_alert just because time has advanced.\n\n"
        "Tool call format:\n"
        f'{{"tool_name":"query_suspicion_of_infection","arguments":{{"stay_id":{stay_id},"t_hour":{t_hour}}}}}\n\n'
        "Final action format:\n"
        '{"action":"keep_monitoring"}\n\n'
        "Valid final actions:\n"
        "- keep_monitoring\n"
        "- infection_suspect\n"
        "- trigger_sepsis_alert\n"
    )
    user_payload = {
        "step_input": {
            "trajectory_id": step_input["trajectory_id"],
            "stay_id": stay_id,
            "step_index": step_input["step_index"],
            "t_hour": t_hour,
            "task_name": task_name,
        },
        "task_mode": step_input.get("task_mode"),
        "tool_backend": step_input.get("tool_backend"),
        "protocol": step_input.get("protocol"),
        "available_tools": toolbox_tools,
        "already_called_tools": executed["tool_calls"],
        "tool_results_by_name": executed["tool_results"],
        "rolling_history": rolling_history,
        "history": history,
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_payload, indent=2)},
    ]


def _zeroshot_exec_calls_used(history: list[dict[str, Any]]) -> int:
    return sum(
        1
        for item in history
        if item["type"] == "tool_call" and item.get("tool_name") in ZEROSHOT_EXEC_TOOL_NAMES
    )


def _summarize_zeroshot_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summarized: list[dict[str, Any]] = []
    for item in history:
        if item["type"] == "tool_call" and item.get("tool_name") == CODE_EXEC_TOOL_NAME:
            payload = item.get("payload", {})
            summarized.append(
                {
                    "type": "python_code",
                    "code": payload.get("arguments", {}).get("code"),
                }
            )
        elif item["type"] == "tool_call" and item.get("tool_name") == SQL_EXEC_TOOL_NAME:
            payload = item.get("payload", {})
            summarized.append(
                {
                    "type": "sql_query",
                    "sql": payload.get("arguments", {}).get("sql"),
                }
            )
        elif item["type"] == "tool_output" and item.get("tool_name") == CODE_EXEC_TOOL_NAME:
            payload = item.get("payload", {})
            summarized.append(
                {
                    "type": "python_output",
                    "ok": payload.get("ok"),
                    "stdout": payload.get("stdout"),
                    "stderr": payload.get("stderr"),
                    "result": payload.get("result"),
                    "error_type": payload.get("error_type"),
                    "error_message": payload.get("error_message"),
                }
            )
        elif item["type"] == "tool_output" and item.get("tool_name") == SQL_EXEC_TOOL_NAME:
            payload = item.get("payload", {})
            summarized.append(
                {
                    "type": "sql_output",
                    "ok": payload.get("ok"),
                    "stdout": payload.get("stdout"),
                    "stderr": payload.get("stderr"),
                    "result": payload.get("result"),
                    "error_type": payload.get("error_type"),
                    "error_message": payload.get("error_message"),
                }
            )
    return summarized


def _build_zeroshot_messages(
    step_input: dict[str, Any],
    history: list[dict[str, Any]],
    guideline_text: str,
) -> list[dict[str, str]]:
    stay_id = int(step_input["stay_id"])
    t_hour = int(step_input["t_hour"])
    task_names = _resolved_task_names(step_input)
    task_name = _single_task_name(step_input)
    if task_names not in (["sepsis"], ["infection_only"]):
        raise ValueError("Zero-shot raw backend currently supports only single-task sepsis or infection-only.")
    max_interactions = int(step_input.get("max_step_interactions") or 4)
    exec_calls_used = _zeroshot_exec_calls_used(history)
    remaining_exec_calls = max(0, max_interactions - exec_calls_used)
    can_execute_more = remaining_exec_calls > 0

    if task_name == "infection_only":
        execution_mode = "sql"
        task_labels = ["keep_monitoring", "infection_suspect"]
        decision_guidance = (
            "Decision guidance:\n"
            "- If suspected infection is not yet visible, prefer keep_monitoring.\n"
            "- If suspected infection is visible from the official antibiotic-culture overlap logic, prefer infection_suspect.\n"
            "- Use mimiciv_hosp.prescriptions.starttime as antibiotic_time.\n"
            "- Use COALESCE(microbiologyevents.charttime, CAST(chartdate AS TIMESTAMP)) as culture_time.\n"
            "- If systemic antibiotics come first, look for a culture within the next 24 hours.\n"
            "- If a culture comes first, look for systemic antibiotics within the next 72 hours.\n"
            "- Use culture time when culture precedes antibiotics; otherwise use antibiotic time.\n"
            "- Ignore culture positivity, organism identity, susceptibilities, and final result status.\n"
            "- Pre-ICU hospital rows from the same admission may already be visible at t_hour=0.\n\n"
        )
        execution_contract = (
            "SQL execution contract:\n"
            "- Use only one read-only SQL statement per turn.\n"
            "- Use only SELECT/WITH/DESCRIBE/SHOW/PRAGMA.\n"
            "- The available mimiciv_hosp tables are already restricted to the current admission and checkpoint visibility window.\n"
            "- For this task, focus on mimiciv_hosp.prescriptions and mimiciv_hosp.microbiologyevents.\n"
            "- Return a compact one-row result with fields such as has_suspected_infection, first_suspicion_time, first_antibiotic_time, first_culture_time.\n"
            "- Prefer one CTE-based query that directly computes the overlap decision.\n\n"
            "Response formats:\n"
            "- To execute SQL, return only one fenced SQL block and nothing else.\n"
            "  Example:\n"
            "  ```sql\n"
            "  WITH abx AS (\n"
            "    SELECT starttime AS antibiotic_time\n"
            "    FROM mimiciv_hosp.prescriptions\n"
            "    WHERE starttime IS NOT NULL\n"
            "  ),\n"
            "  cult AS (\n"
            "    SELECT COALESCE(charttime, CAST(chartdate AS TIMESTAMP)) AS culture_time\n"
            "    FROM mimiciv_hosp.microbiologyevents\n"
            "    WHERE COALESCE(charttime, CAST(chartdate AS TIMESTAMP)) IS NOT NULL\n"
            "  ),\n"
            "  pairs AS (\n"
            "    SELECT\n"
            "      antibiotic_time,\n"
            "      culture_time,\n"
            "      CASE WHEN culture_time <= antibiotic_time THEN culture_time ELSE antibiotic_time END AS suspicion_time\n"
            "    FROM abx\n"
            "    JOIN cult\n"
            "      ON (\n"
            "        culture_time <= antibiotic_time AND antibiotic_time <= culture_time + INTERVAL '72 hours'\n"
            "      ) OR (\n"
            "        antibiotic_time < culture_time AND culture_time <= antibiotic_time + INTERVAL '24 hours'\n"
            "      )\n"
            "  )\n"
            "  SELECT\n"
            "    COUNT(*) > 0 AS has_suspected_infection,\n"
            "    MIN(suspicion_time) AS first_suspicion_time,\n"
            "    MIN(antibiotic_time) AS first_antibiotic_time,\n"
            "    MIN(culture_time) AS first_culture_time\n"
            "  FROM pairs;\n"
            "  ```\n"
            '- To decide, return only one JSON object such as {"action":"keep_monitoring"}.\n'
        )
    else:
        execution_mode = "python"
        task_labels = ["keep_monitoring", "infection_suspect", "trigger_sepsis_alert"]
        decision_guidance = (
            "Decision guidance:\n"
            "- If suspected infection is not yet visible, prefer keep_monitoring.\n"
            "- If suspected infection is visible but visible organ-dysfunction evidence is not yet sufficient for SOFA-style alerting, prefer infection_suspect.\n"
            "- If suspected infection is visible and the visible data supports SOFA >= 2, prefer trigger_sepsis_alert.\n"
            "- Pre-ICU hospital events from the same admission may already be visible at t_hour=0.\n"
            "- For suspected infection, align with the official MIMIC Sepsis-3 operationalization: systemic antibiotics from hospital prescriptions plus microbiology culture timing with asymmetric windows.\n"
            "- Positive culture can support the case but is not required for suspected infection.\n"
            "- For organ dysfunction, use raw SOFA-relevant signals from chartevents, labevents, inputevents, and outputevents.\n\n"
        )
        execution_contract = (
            "Python execution contract:\n"
            "- Use query_db(sql, params=None) for all database access.\n"
            "- query_db is read-only.\n"
            "- Do not open database connections directly.\n"
            "- Preloaded variables: stay_id, subject_id, hadm_id, icu_intime, visible_until, t_hour, pd, np, datetime, timedelta.\n"
            "- Before the code ends, set RESULT to a concise value and/or print concise findings.\n"
            "- Keep snippets short and focused. Prefer one small query at a time.\n"
            "- Prefer SQL filtering and compact helper logic over long hard-coded Python lists.\n"
            "- Never emit giant enumerations of routes, itemids, antibiotics, or repeated literals.\n"
            "- If you need multiple checks, split them across multiple short executions instead of one large script.\n\n"
            "Response formats:\n"
            "- To execute Python, return only one fenced Python block and nothing else.\n"
            "  Example:\n"
            "  ```python\n"
            "  abx = query_db(\"SELECT COUNT(*) AS n FROM mimiciv_hosp.prescriptions WHERE hadm_id = ? AND starttime <= ?\", [hadm_id, visible_until])\n"
            "  RESULT = {\"antibiotic_rows\": int(abx.iloc[0][\"n\"])}\n"
            "  ```\n"
            '- To decide, return only one JSON object such as {"action":"keep_monitoring"}.\n'
        )

    if execution_mode == "sql":
        system_prompt = (
            f"You are an ICU rolling {task_name.replace('_', ' ')} monitoring agent operating directly on raw MIMIC-IV tables.\n"
            "This is a rolling monitoring task, not a forecasting task.\n"
            "At each checkpoint, use only data already visible for this admission.\n"
            "You may either execute exactly one SQL query or return one final action.\n"
            "Do not output reasoning or prose.\n"
            "Return exactly one response and nothing else.\n\n"
            "Task labels:\n"
            + "".join(f"- {label}\n" for label in task_labels)
            + "\n"
            + decision_guidance
            + execution_contract
        )
    else:
        system_prompt = (
            f"You are an ICU rolling {task_name.replace('_', ' ')} monitoring agent operating directly on raw MIMIC-IV tables.\n"
            "This is a rolling monitoring task, not a forecasting task.\n"
            "At each checkpoint, use only data visible up to visible_until for this stay/admission.\n"
            "You may either execute exactly one Python analysis snippet or return one final action.\n"
            "The Python session persists within the current checkpoint only.\n"
            "Do not output reasoning or prose.\n"
            "Return exactly one response and nothing else.\n\n"
            "Task labels:\n"
            + "".join(f"- {label}\n" for label in task_labels)
            + "\n"
            + decision_guidance
            + execution_contract
        )
    if can_execute_more:
        system_prompt += (
            f"\nYou have {remaining_exec_calls} execution(s) remaining before you must commit to a final action."
        )
    else:
        system_prompt += "\nYou have no executions remaining. The next response must be a final action."
    system_prompt += "\n\nGuideline reference:\n" + guideline_text

    user_payload = {
        "step_input": {
            "trajectory_id": step_input["trajectory_id"],
            "stay_id": stay_id,
            "step_index": step_input["step_index"],
            "t_hour": t_hour,
            "task_name": task_name,
        },
        "tool_backend": step_input.get("tool_backend"),
        "allowed_raw_tables": ZEROSHOT_RAW_TABLES,
        "execution_mode": execution_mode,
        "remaining_executions": remaining_exec_calls,
        "history": _summarize_zeroshot_history(history),
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_payload, indent=2)},
    ]


def _build_zeroshot_python_messages(
    step_input: dict[str, Any],
    history: list[dict[str, Any]],
    guideline_text: str,
) -> list[dict[str, str]]:
    stay_id = int(step_input["stay_id"])
    t_hour = int(step_input["t_hour"])
    task_names = _resolved_task_names(step_input)
    if task_names != ["sepsis"]:
        raise ValueError("Zero-shot python backend currently supports only single-task sepsis.")
    max_interactions = int(step_input.get("max_step_interactions") or 4)
    exec_calls_used = _zeroshot_exec_calls_used(history)
    remaining_exec_calls = max(0, max_interactions - exec_calls_used)

    system_prompt = (
        "You are an ICU rolling sepsis monitoring agent operating in a checkpoint-scoped DuckDB Python session.\n"
        "This is a rolling monitoring task, not a forecasting task.\n"
        "At each checkpoint, the visible tables already contain only data available by that checkpoint.\n"
        "You may either execute exactly one short Python snippet or return one final action.\n"
        "The Python session persists within the current checkpoint only.\n"
        "There is no cross-checkpoint rolling_history available in this mode.\n"
        "Do not output reasoning or prose.\n"
        "Return exactly one response and nothing else.\n\n"
        "Task labels:\n"
        "- keep_monitoring\n"
        "- infection_suspect\n"
        "- trigger_sepsis_alert\n\n"
        "Decision guidance:\n"
        "- If suspected infection is not yet visible, prefer keep_monitoring.\n"
        "- If suspected infection is visible but visible organ-dysfunction evidence is not yet sufficient for SOFA-style alerting, prefer infection_suspect.\n"
        "- If suspected infection is visible and the visible data supports SOFA >= 2, prefer trigger_sepsis_alert.\n"
        "- Pre-ICU hospital events from the same admission may already be visible at t_hour=0.\n"
        "- For suspected infection, align with the official MIMIC Sepsis-3 operationalization: systemic antibiotics from hospital prescriptions plus microbiology culture timing with asymmetric windows.\n"
        "- Positive culture can support the case but is not required for suspected infection.\n"
        "- For organ dysfunction, use raw SOFA-relevant signals from chartevents, labevents, inputevents, and outputevents.\n\n"
        "Python execution contract:\n"
        "- Use query_db(sql, params=None) for all database access.\n"
        "- query_db is read-only.\n"
        "- Do not open database connections directly.\n"
        "- The visible tables are already filtered to the current stay/admission and checkpoint; avoid redundant stay/time WHERE clauses unless clinically needed.\n"
        "- Preloaded variables: stay_id, subject_id, hadm_id, visible_until, pd, np, datetime, timedelta.\n"
        "- Before the code ends, set RESULT to a concise value and/or print concise findings.\n"
        "- Keep snippets short and focused. Prefer one small query or one check at a time.\n"
        "- Avoid repeating work already shown in the current checkpoint history.\n"
        "- Do not use triple-quoted SQL. Prefer one-line SQL strings or compact concatenation.\n"
        "- Never emit giant enumerations of routes, itemids, antibiotics, or repeated literals.\n"
        "- If you need multiple checks, split them across multiple short executions instead of one large script.\n\n"
        "Response formats:\n"
        "- To execute Python, return only one CLOSED fenced Python block and nothing else.\n"
        "  Example:\n"
        "  ```python\n"
        "  abx = query_db(\"SELECT COUNT(*) AS n FROM mimiciv_hosp.prescriptions WHERE starttime IS NOT NULL\")\n"
        "  RESULT = {\"antibiotic_rows\": int(abx.iloc[0][\"n\"])}\n"
        "  ```\n"
        '- To decide, return only one JSON object such as {"action":"keep_monitoring"}.\n'
    )
    if remaining_exec_calls > 0:
        system_prompt += (
            f"\nYou have {remaining_exec_calls} Python execution(s) remaining before you must commit to a final action."
        )
    else:
        system_prompt += "\nYou have no Python executions remaining. The next response must be a final action."
    system_prompt += "\n\nGuideline reference:\n" + guideline_text

    user_payload = {
        "step_input": {
            "trajectory_id": step_input["trajectory_id"],
            "stay_id": stay_id,
            "step_index": step_input["step_index"],
            "t_hour": t_hour,
            "task_name": "sepsis",
        },
        "tool_backend": step_input.get("tool_backend"),
        "allowed_raw_tables": ZEROSHOT_RAW_TABLES,
        "remaining_python_executions": remaining_exec_calls,
        "history": _summarize_zeroshot_history(history),
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_payload, indent=2)},
    ]


def _build_zeroshot_repair_messages(
    step_input: dict[str, Any],
    history: list[dict[str, Any]],
    guideline_text: str,
    bad_output: str,
) -> list[dict[str, str]]:
    messages = _build_zeroshot_messages(step_input, history, guideline_text)
    messages.append({"role": "assistant", "content": bad_output})
    remaining_code_calls = max(
        0,
        int(step_input.get("max_step_interactions") or 4) - _zeroshot_exec_calls_used(history),
    )
    execution_mode = "sql" if _single_task_name(step_input) == "infection_only" else "python"
    if remaining_code_calls > 0:
        if execution_mode == "sql":
            repair_hint = (
                "Your previous reply was invalid or too long. Respond again with exactly one response and no extra text. "
                "If you need execution, return only one short fenced SQL block. "
                'If you are ready to decide, return only one JSON object such as {"action":"keep_monitoring"}. '
                "Do not wrap SQL in JSON."
            )
        else:
            repair_hint = (
                "Your previous reply was invalid or too long. Respond again with exactly one response and no extra text. "
                "If you need code execution, return only one short fenced Python block. "
                'If you are ready to decide, return only one JSON object such as {"action":"keep_monitoring"}. '
                "Do not wrap Python in JSON, and avoid long literal lists."
            )
    else:
        repair_hint = (
            "Your previous reply was invalid. Respond again with JSON only and no extra text. "
            'You must now return a final action such as {"action":"infection_suspect"}.'
        )
    messages.append({"role": "user", "content": repair_hint})
    return messages


def _build_zeroshot_python_repair_messages(
    step_input: dict[str, Any],
    history: list[dict[str, Any]],
    guideline_text: str,
    bad_output: str,
) -> list[dict[str, str]]:
    messages = _build_zeroshot_python_messages(step_input, history, guideline_text)
    messages.append({"role": "assistant", "content": bad_output})
    remaining_code_calls = max(
        0,
        int(step_input.get("max_step_interactions") or 4) - _zeroshot_exec_calls_used(history),
    )
    if remaining_code_calls > 0:
        repair_hint = (
            "Your previous reply was invalid, incomplete, or too long. Respond again with exactly one response and no extra text. "
            "If you need code execution, return only one short CLOSED fenced Python block. "
            'If you are ready to decide, return only one JSON object such as {"action":"keep_monitoring"}. '
            "Do not wrap Python in JSON, do not continue a truncated script, and avoid triple-quoted SQL."
        )
    else:
        repair_hint = (
            "Your previous reply was invalid. Respond again with JSON only and no extra text. "
            'You must now return a final action such as {"action":"infection_suspect"}.'
        )
    messages.append({"role": "user", "content": repair_hint})
    return messages


def _sanitize_model_text(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()


def _extract_json_object(text: str) -> dict[str, Any]:
    text = _sanitize_model_text(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for match in re.finditer(r"\{", text):
            try:
                payload, _ = decoder.raw_decode(text[match.start() :])
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
        raise ValueError(f"Model did not return JSON: {text}")


def _extract_python_code_block(text: str, *, allow_open: bool = True) -> str | None:
    text = _sanitize_model_text(text)
    closed_match = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if closed_match:
        code = closed_match.group(1).strip()
        return code or None

    tag_match = re.search(r"<python>\s*(.*?)\s*</python>", text, re.DOTALL | re.IGNORECASE)
    if tag_match:
        code = tag_match.group(1).strip()
        return code or None

    if allow_open:
        open_match = re.search(r"```(?:python)?\s*\n(.*)\Z", text, re.DOTALL | re.IGNORECASE)
        if open_match:
            code = open_match.group(1).strip()
            return code or None

        open_tag_match = re.search(r"<python>\s*(.*)\Z", text, re.DOTALL | re.IGNORECASE)
        if open_tag_match:
            code = open_tag_match.group(1).strip()
            return code or None

    return None


def _extract_sql_code_block(text: str) -> str | None:
    text = _sanitize_model_text(text)
    closed_match = re.search(r"```sql\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if closed_match:
        sql = closed_match.group(1).strip()
        return sql or None

    open_match = re.search(r"```sql\s*\n(.*)\Z", text, re.DOTALL | re.IGNORECASE)
    if open_match:
        sql = open_match.group(1).strip()
        return sql or None
    return None


def _extract_zeroshot_response(
    text: str,
    *,
    allowed_actions: list[str] | None = None,
    execution_mode: str = "python",
    allow_open_python: bool = True,
) -> ToolCall | ActionDecision:
    if execution_mode == "sql":
        sql = _extract_sql_code_block(text)
        if sql is not None:
            return ToolCall(tool_name=SQL_EXEC_TOOL_NAME, arguments={"sql": sql})
    else:
        code = _extract_python_code_block(text, allow_open=allow_open_python)
        if code is not None:
            return ToolCall(tool_name=CODE_EXEC_TOOL_NAME, arguments={"code": code})
    return _coerce_zeroshot_output(
        _extract_json_object(text),
        allowed_actions=allowed_actions,
        execution_mode=execution_mode,
    )


def _compile_zeroshot_python_response(response: ToolCall | ActionDecision) -> ToolCall | ActionDecision:
    if isinstance(response, ToolCall) and response.tool_name == CODE_EXEC_TOOL_NAME:
        code = response.arguments.get("code")
        if not isinstance(code, str) or not code.strip():
            raise ValueError("python_code must be a non-empty string.")
        compile(code, "<model>", "exec")
    return response


def _build_repair_messages(
    step_input: dict[str, Any],
    history: list[dict[str, Any]],
    available_tools: list[str],
    bad_output: str,
) -> list[dict[str, str]]:
    if _is_toolbox_protocol(step_input):
        return _build_toolbox_repair_messages(step_input, history, available_tools, bad_output)
    messages = _build_messages(step_input, history, available_tools)
    messages.append({"role": "assistant", "content": bad_output})
    stay_id = int(step_input["stay_id"])
    t_hour = int(step_input["t_hour"])
    next_tool = _next_missing_tool_for_step(step_input, history, available_tools)
    if _is_multitask_step(step_input):
        if next_tool is not None:
            repair_hint = (
                "Your previous reply was invalid. Respond again with JSON only and no extra text. "
                f'Call the required next tool now: {{"tool_name":"{next_tool}","arguments":{{"stay_id":{stay_id},"t_hour":{t_hour}}}}}'
            )
        else:
            repair_hint = (
                "Your previous reply was invalid. Respond again with JSON only and no extra text. "
                'Return final task actions now as {"task_actions":{"sepsis":"keep_monitoring","aki":"keep_monitoring","respiratory_support":"room_air_or_low_support"}}.'
            )
    else:
        if next_tool is not None:
            repair_hint = (
                "Your previous reply was invalid because it was not exactly one JSON object. "
                "Respond again with JSON only and no extra text. "
                f'Call the required next tool now: {{"tool_name":"{next_tool}","arguments":{{"stay_id":{stay_id},"t_hour":{t_hour}}}}}.'
            )
        else:
            repair_hint = (
                "Your previous reply was invalid because it was not exactly one JSON object. "
                'Respond again with JSON only and no extra text. Use {"action":"keep_monitoring"} style.'
            )
    messages.append({"role": "user", "content": repair_hint})
    return messages


def _build_toolbox_repair_messages(
    step_input: dict[str, Any],
    history: list[dict[str, Any]],
    available_tools: list[str],
    bad_output: str,
) -> list[dict[str, str]]:
    messages = _build_toolbox_messages(step_input, history, available_tools)
    messages.append({"role": "assistant", "content": bad_output})
    stay_id = int(step_input["stay_id"])
    t_hour = int(step_input["t_hour"])
    repair_hint = (
        "Your previous reply was invalid. Respond again with JSON only and no extra text. "
        "Return either one allowed tool call or one final action. "
        f"Allowed tools: {', '.join(tool_name for tool_name in available_tools if tool_name in SEPSIS_TOOLBOX_TOOL_NAMES)}. "
        f'Example tool call: {{"tool_name":"query_sofa","arguments":{{"stay_id":{stay_id},"t_hour":{t_hour}}}}}. '
        'Example final action: {"action":"infection_suspect"}.'
    )
    messages.append({"role": "user", "content": repair_hint})
    return messages


def _coerce_agent_output(payload: dict[str, Any]) -> ToolCall | ActionDecision:
    if "task_actions" in payload:
        task_actions = payload["task_actions"]
        if not isinstance(task_actions, dict):
            raise ValueError(f"Invalid task_actions payload: {task_actions}")
        task_actions = _normalize_task_actions(task_actions)
        expected_keys = {"sepsis", "aki", "respiratory_support"}
        if set(task_actions) != expected_keys:
            raise ValueError(f"Invalid task_actions keys: {sorted(task_actions)}")
        for action in task_actions.values():
            if action not in ACTIONS:
                raise ValueError(f"Invalid task action: {action}")
        return ActionDecision(task_actions=task_actions)
    if "action" in payload:
        action = payload["action"]
        if action not in ACTIONS:
            raise ValueError(f"Invalid action: {action}")
        return ActionDecision(action=action)
    if "tool_name" in payload:
        return ToolCall(tool_name=payload["tool_name"], arguments=payload.get("arguments", {}))
    raise ValueError(f"Unrecognized agent payload: {payload}")


def _coerce_zeroshot_output(
    payload: dict[str, Any],
    *,
    allowed_actions: list[str] | None = None,
    execution_mode: str = "python",
) -> ToolCall | ActionDecision:
    has_action = "action" in payload
    has_code = "python_code" in payload
    has_sql = "sql_code" in payload
    if sum(int(flag) for flag in (has_action, has_code, has_sql)) != 1:
        raise ValueError("Zero-shot response must contain exactly one of 'action', 'python_code', or 'sql_code'.")
    if has_action:
        action = payload["action"]
        valid_actions = allowed_actions or TASK_LABEL_SPACES["sepsis"]
        if action not in valid_actions:
            raise ValueError(f"Invalid action: {action}")
        return ActionDecision(action=action)
    if execution_mode == "sql":
        sql = payload.get("sql_code")
        if not isinstance(sql, str) or not sql.strip():
            raise ValueError("sql_code must be a non-empty string.")
        return ToolCall(tool_name=SQL_EXEC_TOOL_NAME, arguments={"sql": sql})
    code = payload.get("python_code")
    if not isinstance(code, str) or not code.strip():
        raise ValueError("python_code must be a non-empty string.")
    return ToolCall(tool_name=CODE_EXEC_TOOL_NAME, arguments={"code": code})


def _normalize_toolbox_response(
    response: ToolCall | ActionDecision,
    *,
    step_input: dict[str, Any],
    available_tools: list[str],
) -> ToolCall | ActionDecision:
    if isinstance(response, ActionDecision):
        if response.task_actions is not None:
            raise ValueError("rolling_toolbox_with_history expects a single final action, not task_actions.")
        return response
    if response.tool_name not in available_tools:
        raise ValueError(f"Tool '{response.tool_name}' is not available in rolling_toolbox_with_history.")
    return ToolCall(
        tool_name=response.tool_name,
        arguments={"stay_id": int(step_input["stay_id"]), "t_hour": int(step_input["t_hour"])},
    )


@dataclass(slots=True)
class HeuristicAgent:
    sofa_alert_threshold: int = 2
    aki_alert_threshold: int = 2

    def next_response(
        self,
        step_input: dict[str, Any],
        history: list[dict[str, Any]],
        available_tools: list[str],
    ) -> ToolCall | ActionDecision:
        task_names = _resolved_task_names(step_input)
        if len(task_names) > 1:
            return self._next_multitask_response(step_input, history, available_tools)
        task_name = task_names[0]
        if task_name in {"sepsis", "infection_only"}:
            return self._next_sepsis_response(step_input, history, available_tools)
        if task_name == "aki":
            return self._next_aki_response(step_input, history, available_tools)
        if task_name == "respiratory_support":
            return self._next_respiratory_response(step_input, history, available_tools)
        raise ValueError(f"Unsupported single-task mode: {task_name}")

    def _latest_tool_output(self, history: list[dict[str, Any]], stay_id: int, key: str) -> dict[str, Any] | None:
        tool_outputs = [item["payload"] for item in history if item["type"] == "tool_output"]
        return next(
            (item for item in reversed(tool_outputs) if item.get("stay_id") == stay_id and key in item),
            None,
        )

    def _next_sepsis_response(
        self,
        step_input: dict[str, Any],
        history: list[dict[str, Any]],
        available_tools: list[str],
    ) -> ToolCall | ActionDecision:
        t_hour = int(step_input["t_hour"])
        stay_id = int(step_input["stay_id"])
        seen_tools = {item["tool_name"] for item in history if item["type"] == "tool_call"}
        task_name = _single_task_name(step_input)
        label_space = _label_space_for_task(step_input, task_name)

        infection_output = self._latest_tool_output(history, stay_id, "has_suspected_infection")
        sofa_output = self._latest_tool_output(history, stay_id, "latest_sofa_24hours")

        if "query_suspicion_of_infection" in available_tools and "query_suspicion_of_infection" not in seen_tools:
            return ToolCall(
                tool_name="query_suspicion_of_infection",
                arguments={"stay_id": stay_id, "t_hour": t_hour},
            )
        if infection_output and infection_output.get("has_suspected_infection"):
            if "trigger_sepsis_alert" in label_space and "query_sofa" in available_tools and "query_sofa" not in seen_tools:
                return ToolCall(tool_name="query_sofa", arguments={"stay_id": stay_id, "t_hour": t_hour})
            latest_sofa = (sofa_output or {}).get("latest_sofa_24hours")
            if "trigger_sepsis_alert" in label_space and latest_sofa is not None and latest_sofa >= self.sofa_alert_threshold:
                return ActionDecision(action="trigger_sepsis_alert")
            return ActionDecision(action="infection_suspect")
        return ActionDecision(action="keep_monitoring")

    def _next_multitask_response(
        self,
        step_input: dict[str, Any],
        history: list[dict[str, Any]],
        available_tools: list[str],
    ) -> ToolCall | ActionDecision:
        t_hour = int(step_input["t_hour"])
        stay_id = int(step_input["stay_id"])
        seen_tools = {item["tool_name"] for item in history if item["type"] == "tool_call"}

        tool_order = [
            "query_suspicion_of_infection",
            "query_sofa",
            "query_kdigo_stage",
            "query_ventilation_status",
        ]
        for tool_name in tool_order:
            if tool_name in available_tools and tool_name not in seen_tools:
                return ToolCall(tool_name=tool_name, arguments={"stay_id": stay_id, "t_hour": t_hour})

        infection_output = self._latest_tool_output(history, stay_id, "has_suspected_infection") or {}
        sofa_output = self._latest_tool_output(history, stay_id, "latest_sofa_24hours") or {}
        kdigo_output = self._latest_tool_output(history, stay_id, "latest_aki_stage_smoothed") or {}
        vent_output = self._latest_tool_output(history, stay_id, "current_support_level") or {}

        if infection_output.get("has_suspected_infection"):
            latest_sofa = sofa_output.get("latest_sofa_24hours")
            if latest_sofa is not None and latest_sofa >= self.sofa_alert_threshold:
                sepsis_action = "trigger_sepsis_alert"
            else:
                sepsis_action = "infection_suspect"
        else:
            sepsis_action = "keep_monitoring"

        latest_aki = kdigo_output.get("latest_aki_stage_smoothed")
        if latest_aki is not None and latest_aki >= self.aki_alert_threshold:
            aki_action = "trigger_aki_alert"
        elif latest_aki is not None and latest_aki >= 1:
            aki_action = "suspect_aki"
        else:
            aki_action = "keep_monitoring"

        resp_action = vent_output.get("highest_support_level_so_far", "room_air_or_low_support")
        return ActionDecision(
            task_actions={
                "sepsis": sepsis_action,
                "aki": aki_action,
                "respiratory_support": resp_action,
            }
        )

    def _next_aki_response(
        self,
        step_input: dict[str, Any],
        history: list[dict[str, Any]],
        available_tools: list[str],
    ) -> ToolCall | ActionDecision:
        t_hour = int(step_input["t_hour"])
        stay_id = int(step_input["stay_id"])
        seen_tools = {item["tool_name"] for item in history if item["type"] == "tool_call"}
        if "query_kdigo_stage" in available_tools and "query_kdigo_stage" not in seen_tools:
            return ToolCall(tool_name="query_kdigo_stage", arguments={"stay_id": stay_id, "t_hour": t_hour})
        kdigo_output = self._latest_tool_output(history, stay_id, "latest_aki_stage_smoothed") or {}
        latest_aki = kdigo_output.get("latest_aki_stage_smoothed")
        label_space = _label_space_for_task(step_input, "aki")
        if "aki_stage_1" in label_space:
            stage_label = kdigo_output.get("current_aki_state_label")
            if stage_label is None:
                stage_label = {
                    0: "no_aki",
                    1: "aki_stage_1",
                    2: "aki_stage_2",
                    3: "aki_stage_3",
                }.get(latest_aki if latest_aki is not None else 0, "aki_stage_3")
            return ActionDecision(action=stage_label)
        if latest_aki is not None and latest_aki >= self.aki_alert_threshold:
            return ActionDecision(action="trigger_aki_alert")
        if latest_aki is not None and latest_aki >= 1:
            return ActionDecision(action="suspect_aki")
        return ActionDecision(action="keep_monitoring")

    def _next_respiratory_response(
        self,
        step_input: dict[str, Any],
        history: list[dict[str, Any]],
        available_tools: list[str],
    ) -> ToolCall | ActionDecision:
        t_hour = int(step_input["t_hour"])
        stay_id = int(step_input["stay_id"])
        seen_tools = {item["tool_name"] for item in history if item["type"] == "tool_call"}
        if "query_ventilation_status" in available_tools and "query_ventilation_status" not in seen_tools:
            return ToolCall(
                tool_name="query_ventilation_status",
                arguments={"stay_id": stay_id, "t_hour": t_hour},
            )
        vent_output = self._latest_tool_output(history, stay_id, "current_support_level") or {}
        return ActionDecision(action=vent_output.get("highest_support_level_so_far", "room_air_or_low_support"))


@dataclass(slots=True)
class LocalQwenChat:
    model_ref: str = "Qwen/Qwen3.5-9B"
    temperature: float = 0.0
    top_p: float = 0.95
    max_new_tokens: int = 250
    tokenizer: Any = field(init=False, repr=False)
    model: Any = field(init=False, repr=False)
    torch: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError("Running the local Qwen agent requires 'torch' to be installed.") from exc

        self.model_ref = os.environ.get("QWEN_MODEL", self.model_ref)
        offline = os.environ.get("QWEN_OFFLINE", "0") == "1"
        revision = os.environ.get("QWEN_REVISION")

        allow_cpu = os.environ.get("QWEN_ALLOW_CPU", "0") == "1"
        if torch.cuda.is_available():
            device_map = "auto"
            dtype = torch.float16
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            device_map = {"": "mps"}
            dtype = torch.float16
        elif allow_cpu:
            device_map = {"": "cpu"}
            dtype = torch.float32
        else:
            raise RuntimeError(
                "No CUDA or MPS accelerator found for local Qwen inference. "
                "Use a GPU-enabled environment, or set QWEN_ALLOW_CPU=1 to force CPU loading."
            )

        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError("Running the local Qwen agent requires 'transformers' to be installed.") from exc

        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_ref,
            trust_remote_code=True,
            use_fast=True,
            revision=revision,
            local_files_only=offline,
        )

        self.torch = torch
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_ref,
            torch_dtype=dtype,
            device_map=device_map,
            trust_remote_code=True,
            revision=revision,
            local_files_only=offline,
        )
        self.model.eval()

    @property
    def device(self):
        if hasattr(self.model, "device"):
            return self.model.device
        return next(self.model.parameters()).device

    def generate(self, messages: list[dict[str, str]]) -> str:
        if hasattr(self.tokenizer, "apply_chat_template"):
            prompt = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = self.tokenizer(prompt, return_tensors="pt")
        else:
            prompt = ""
            for message in messages:
                prompt += f"[{message['role'].upper()}]\n{message.get('content', '')}\n"
            prompt += "[ASSISTANT]\n"
            inputs = self.tokenizer(prompt, return_tensors="pt")

        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        do_sample = self.temperature > 0

        with self.torch.no_grad():
            output = self.model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=do_sample,
                temperature=self.temperature if do_sample else None,
                top_p=self.top_p if do_sample else None,
                eos_token_id=self.tokenizer.eos_token_id,
            )

        generated = output[0][inputs["input_ids"].shape[-1] :]
        text = self.tokenizer.decode(generated, skip_special_tokens=True)
        return text.strip()


def _default_zeroshot_guideline_path() -> Path:
    return Path(__file__).resolve().parents[2] / "baseline" / "sepsis_raw_tables_guideline.yaml"


def _load_zeroshot_guideline_text(path: str | None) -> str:
    if path is None:
        return ""
    guideline_path = Path(path) if path else _default_zeroshot_guideline_path()
    if not guideline_path.is_absolute():
        guideline_path = Path.cwd() / guideline_path
    if not guideline_path.exists():
        return f"# Guideline file not found: {guideline_path}"
    return guideline_path.read_text()


@dataclass(slots=True)
class QwenChatAgent:
    model: str = "Qwen/Qwen3.5-9B"
    temperature: float = 0.0
    top_p: float = 0.95
    max_new_tokens: int = 250
    repair_max_new_tokens: int | None = None
    zeroshot_guideline_path: str | None = None
    trace_callback: Callable[[dict[str, Any]], None] | None = field(default=None, repr=False)
    client: LocalQwenChat = field(init=False, repr=False)
    zeroshot_guideline_text: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.client = LocalQwenChat(
            model_ref=self.model,
            temperature=self.temperature,
            top_p=self.top_p,
            max_new_tokens=self.max_new_tokens,
        )
        if self.repair_max_new_tokens is None:
            self.repair_max_new_tokens = max(240, min(self.max_new_tokens, 800))
        self.zeroshot_guideline_text = _load_zeroshot_guideline_text(self.zeroshot_guideline_path)

    def next_response(
        self,
        step_input: dict[str, Any],
        history: list[dict[str, Any]],
        available_tools: list[str],
    ) -> ToolCall | ActionDecision:
        if step_input.get("tool_backend") == "zeroshot_python":
            return self._next_zeroshot_python_response(step_input, history)
        if step_input.get("tool_backend") in {"zeroshot_sql", "zeroshot_raw"}:
            return self._next_zeroshot_response(step_input, history)
        if _is_toolbox_protocol(step_input):
            return self._next_toolbox_response(step_input, history, available_tools)
        context = {
            "trajectory_id": step_input["trajectory_id"],
            "stay_id": int(step_input["stay_id"]),
            "step_index": int(step_input["step_index"]),
            "t_hour": int(step_input["t_hour"]),
        }
        next_tool = _next_missing_tool_for_step(step_input, history, available_tools)
        messages = _build_messages(step_input, history, available_tools)
        content = self.client.generate(messages)
        if self.trace_callback is not None:
            self.trace_callback({"event_type": "model_output_raw", **context, "output": content})
        try:
            response = _coerce_agent_output(_extract_json_object(content))
        except (ValueError, json.JSONDecodeError):
            original_max_tokens = self.client.max_new_tokens
            repair_messages = _build_repair_messages(step_input, history, available_tools, content)
            self.client.max_new_tokens = self.repair_max_new_tokens
            try:
                repaired = self.client.generate(repair_messages)
            finally:
                self.client.max_new_tokens = original_max_tokens
            if self.trace_callback is not None:
                self.trace_callback({"event_type": "model_output_repair", **context, "output": repaired})
            response = _coerce_agent_output(_extract_json_object(repaired))

        if next_tool is None and isinstance(response, ToolCall):
            original_max_tokens = self.client.max_new_tokens
            repair_messages = _build_repair_messages(step_input, history, available_tools, content)
            self.client.max_new_tokens = self.repair_max_new_tokens
            try:
                repaired = self.client.generate(repair_messages)
            finally:
                self.client.max_new_tokens = original_max_tokens
            if self.trace_callback is not None:
                self.trace_callback(
                    {
                        "event_type": "model_output_repair_final_decision",
                        **context,
                        "output": repaired,
                    }
                )
            response = _coerce_agent_output(_extract_json_object(repaired))

        if next_tool is not None and (
            not isinstance(response, ToolCall) or response.tool_name != next_tool
        ):
            if self.trace_callback is not None:
                self.trace_callback(
                    {
                        "event_type": "model_output_forced_tool",
                        **context,
                        "required_tool_name": next_tool,
                        "original_response": (
                            {"task_actions": response.task_actions}
                            if isinstance(response, ActionDecision) and response.task_actions is not None
                            else {"action": response.action}
                            if isinstance(response, ActionDecision)
                            else {"tool_name": response.tool_name, "arguments": response.arguments}
                        ),
                    }
                )
            return ToolCall(
                tool_name=next_tool,
                arguments={"stay_id": int(step_input["stay_id"]), "t_hour": int(step_input["t_hour"])},
            )
        if next_tool is not None and isinstance(response, ToolCall):
            return ToolCall(
                tool_name=next_tool,
                arguments={"stay_id": int(step_input["stay_id"]), "t_hour": int(step_input["t_hour"])},
            )
        return response

    def _next_toolbox_response(
        self,
        step_input: dict[str, Any],
        history: list[dict[str, Any]],
        available_tools: list[str],
    ) -> ToolCall | ActionDecision:
        context = {
            "trajectory_id": step_input["trajectory_id"],
            "stay_id": int(step_input["stay_id"]),
            "step_index": int(step_input["step_index"]),
            "t_hour": int(step_input["t_hour"]),
        }
        messages = _build_toolbox_messages(step_input, history, available_tools)
        content = self.client.generate(messages)
        if self.trace_callback is not None:
            self.trace_callback({"event_type": "model_output_raw", **context, "output": content})
        try:
            response = _normalize_toolbox_response(
                _coerce_agent_output(_extract_json_object(content)),
                step_input=step_input,
                available_tools=available_tools,
            )
        except (ValueError, json.JSONDecodeError):
            original_max_tokens = self.client.max_new_tokens
            repair_messages = _build_toolbox_repair_messages(step_input, history, available_tools, content)
            self.client.max_new_tokens = self.repair_max_new_tokens
            try:
                repaired = self.client.generate(repair_messages)
            finally:
                self.client.max_new_tokens = original_max_tokens
            if self.trace_callback is not None:
                self.trace_callback({"event_type": "model_output_repair", **context, "output": repaired})
            response = _normalize_toolbox_response(
                _coerce_agent_output(_extract_json_object(repaired)),
                step_input=step_input,
                available_tools=available_tools,
            )
        return response

    def _next_zeroshot_response(
        self,
        step_input: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> ToolCall | ActionDecision:
        task_name = _single_task_name(step_input)
        allowed_actions = _label_space_for_task(step_input, task_name)
        execution_mode = "sql" if task_name == "infection_only" else "python"
        context = {
            "trajectory_id": step_input["trajectory_id"],
            "stay_id": int(step_input["stay_id"]),
            "step_index": int(step_input["step_index"]),
            "t_hour": int(step_input["t_hour"]),
        }
        messages = _build_zeroshot_messages(step_input, history, self.zeroshot_guideline_text)
        content = self.client.generate(messages)
        if self.trace_callback is not None:
            self.trace_callback({"event_type": "model_output_raw", **context, "output": content})
        try:
            response = _extract_zeroshot_response(
                content,
                allowed_actions=allowed_actions,
                execution_mode=execution_mode,
            )
        except (ValueError, json.JSONDecodeError):
            original_max_tokens = self.client.max_new_tokens
            repair_messages = _build_zeroshot_repair_messages(
                step_input,
                history,
                self.zeroshot_guideline_text,
                content,
            )
            self.client.max_new_tokens = self.repair_max_new_tokens
            try:
                repaired = self.client.generate(repair_messages)
            finally:
                self.client.max_new_tokens = original_max_tokens
            if self.trace_callback is not None:
                self.trace_callback({"event_type": "model_output_repair", **context, "output": repaired})
            response = _extract_zeroshot_response(
                repaired,
                allowed_actions=allowed_actions,
                execution_mode=execution_mode,
            )

        remaining_code_calls = max(
            0,
            int(step_input.get("max_step_interactions") or 4) - _zeroshot_exec_calls_used(history),
        )
        if remaining_code_calls == 0 and isinstance(response, ToolCall):
            original_max_tokens = self.client.max_new_tokens
            repair_messages = _build_zeroshot_repair_messages(
                step_input,
                history,
                self.zeroshot_guideline_text,
                content,
            )
            self.client.max_new_tokens = self.repair_max_new_tokens
            try:
                repaired = self.client.generate(repair_messages)
            finally:
                self.client.max_new_tokens = original_max_tokens
            if self.trace_callback is not None:
                self.trace_callback(
                    {
                        "event_type": "model_output_repair_final_decision",
                        **context,
                        "output": repaired,
                    }
                )
            response = _extract_zeroshot_response(
                repaired,
                allowed_actions=allowed_actions,
                execution_mode=execution_mode,
            )
            if isinstance(response, ToolCall):
                raise ValueError("Zero-shot agent must return a final action after code budget is exhausted.")

        return response

    def _next_zeroshot_python_response(
        self,
        step_input: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> ToolCall | ActionDecision:
        allowed_actions = _label_space_for_task(step_input, "sepsis")
        context = {
            "trajectory_id": step_input["trajectory_id"],
            "stay_id": int(step_input["stay_id"]),
            "step_index": int(step_input["step_index"]),
            "t_hour": int(step_input["t_hour"]),
        }
        messages = _build_zeroshot_python_messages(step_input, history, self.zeroshot_guideline_text)
        content = self.client.generate(messages)
        if self.trace_callback is not None:
            self.trace_callback({"event_type": "model_output_raw", **context, "output": content})
        try:
            response = _compile_zeroshot_python_response(
                _extract_zeroshot_response(
                    content,
                    allowed_actions=allowed_actions,
                    execution_mode="python",
                    allow_open_python=False,
                )
            )
        except (ValueError, json.JSONDecodeError, SyntaxError):
            original_max_tokens = self.client.max_new_tokens
            repair_messages = _build_zeroshot_python_repair_messages(
                step_input,
                history,
                self.zeroshot_guideline_text,
                content,
            )
            self.client.max_new_tokens = self.repair_max_new_tokens
            try:
                repaired = self.client.generate(repair_messages)
            finally:
                self.client.max_new_tokens = original_max_tokens
            if self.trace_callback is not None:
                self.trace_callback({"event_type": "model_output_repair", **context, "output": repaired})
            response = _compile_zeroshot_python_response(
                _extract_zeroshot_response(
                    repaired,
                    allowed_actions=allowed_actions,
                    execution_mode="python",
                    allow_open_python=False,
                )
            )

        remaining_code_calls = max(
            0,
            int(step_input.get("max_step_interactions") or 4) - _zeroshot_exec_calls_used(history),
        )
        if remaining_code_calls == 0 and isinstance(response, ToolCall):
            original_max_tokens = self.client.max_new_tokens
            repair_messages = _build_zeroshot_python_repair_messages(
                step_input,
                history,
                self.zeroshot_guideline_text,
                content,
            )
            self.client.max_new_tokens = self.repair_max_new_tokens
            try:
                repaired = self.client.generate(repair_messages)
            finally:
                self.client.max_new_tokens = original_max_tokens
            if self.trace_callback is not None:
                self.trace_callback(
                    {
                        "event_type": "model_output_repair_final_decision",
                        **context,
                        "output": repaired,
                    }
                )
            response = _compile_zeroshot_python_response(
                _extract_zeroshot_response(
                    repaired,
                    allowed_actions=allowed_actions,
                    execution_mode="python",
                    allow_open_python=False,
                )
            )
            if isinstance(response, ToolCall):
                raise ValueError("Zero-shot python agent must return a final action after code budget is exhausted.")

        return response
