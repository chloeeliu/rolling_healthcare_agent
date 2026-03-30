from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .schemas import ACTIONS, ActionDecision, ToolCall


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


MULTITASK_TOOL_ORDER = [
    "query_suspicion_of_infection",
    "query_sofa",
    "query_kdigo_stage",
    "query_ventilation_status",
]


def _next_missing_tool(history: list[dict[str, Any]], available_tools: list[str]) -> str | None:
    seen_tools = [item["tool_name"] for item in history if item["type"] == "tool_call"]
    seen_set = set(seen_tools)
    for tool_name in MULTITASK_TOOL_ORDER:
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


def _build_messages(
    step_input: dict[str, Any],
    history: list[dict[str, Any]],
    available_tools: list[str],
) -> list[dict[str, str]]:
    if _is_multitask_step(step_input):
        next_tool = _next_missing_tool(history, available_tools)
        seen_tools = {item["tool_name"] for item in history if item["type"] == "tool_call"}
        remaining_tools = [
            tool_name for tool_name in MULTITASK_TOOL_ORDER if tool_name in available_tools and tool_name not in seen_tools
        ]
        executed = _summarize_history(history)
        stay_id = int(step_input["stay_id"])
        t_hour = int(step_input["t_hour"])
        system_prompt = (
            "You are an ICU rolling multi-task surveillance agent.\n"
            "Monitored tasks: sepsis, aki, respiratory_support.\n"
            "At each checkpoint, you may either call exactly one tool or return final task decisions.\n"
            "Use only the allowed tools and use them in the required order.\n"
            "Do not output reasoning, analysis, markdown, or <think> tags.\n"
            "Return exactly one JSON object and nothing else.\n\n"
            "Task semantics:\n"
            "- sepsis: keep_monitoring | infection_suspect | trigger_sepsis_alert\n"
            "- aki: keep_monitoring | suspect_aki | trigger_aki_alert\n"
            "- respiratory_support: room_air_or_low_support | "
            "high_flow_or_noninvasive_support | invasive_vent_required\n\n"
            "Tool semantics:\n"
            "- query_suspicion_of_infection: infection evidence visible by this checkpoint\n"
            "- query_sofa: current visible SOFA summary up to this checkpoint\n"
            "- query_kdigo_stage: current visible AKI stage summary up to this checkpoint\n"
            "- query_ventilation_status: current and highest visible respiratory support up to this checkpoint\n\n"
            "Recommended decision pattern:\n"
            "1. Check infection and sofa for sepsis.\n"
            "2. Check kdigo for AKI.\n"
            "3. Check ventilation for respiratory support.\n"
            "4. Return one decision for every task in a fixed key order.\n\n"
            "Important:\n"
            "- Evidence may already be visible at t_hour=0 because some events can happen before ICU admission.\n"
            "- Do not assume keep_monitoring just because t_hour is small.\n"
            "- Do not omit any task.\n"
            "- The final JSON must contain exactly these keys in task_actions: "
            "sepsis, aki, respiratory_support.\n"
            "- Before returning task_actions, collect all four tool outputs for the current checkpoint.\n"
            "- If any required tool is still missing, your next response must be a tool call for the first missing tool.\n"
            "- Never repeat a completed tool call.\n"
            "- Never guess a final decision before all four tool outputs are visible.\n\n"
            "Tool call format:\n"
            f'{{"tool_name":"query_kdigo_stage","arguments":{{"stay_id":{stay_id},"t_hour":{t_hour}}}}}\n\n'
            "Final decision format:\n"
            '{"task_actions":{"sepsis":"keep_monitoring","aki":"keep_monitoring","respiratory_support":"room_air_or_low_support"}}'
        )
        if next_tool is not None:
            system_prompt += (
                f"\n\nCurrent requirement: the next response must be a tool call for `{next_tool}`."
            )
        else:
            system_prompt += "\n\nCurrent requirement: all tool outputs are available, so the next response must be final task_actions."
        user_payload = {
            "step_input": {
                "trajectory_id": step_input["trajectory_id"],
                "stay_id": stay_id,
                "step_index": step_input["step_index"],
                "t_hour": t_hour,
            },
            "available_tools": available_tools,
            "required_tool_order": remaining_tools,
            "already_called_tools": executed["tool_calls"],
            "tool_results_by_name": executed["tool_results"],
            "next_required_tool": next_tool,
        }
    else:
        stay_id = int(step_input["stay_id"])
        t_hour = int(step_input["t_hour"])
        system_prompt = (
            "You are an ICU rolling sepsis surveillance agent.\n"
            "Use only the allowed tools.\n"
            "Do not output reasoning, analysis, markdown, or <think> tags.\n"
            "Return exactly one JSON object and nothing else.\n"
            "Check infection first, then sofa if infection is present.\n"
            "Evidence may already be visible at t_hour=0.\n\n"
            "Tool call format:\n"
            f'{{"tool_name":"query_suspicion_of_infection","arguments":{{"stay_id":{stay_id},"t_hour":{t_hour}}}}}\n\n'
            "Final action format:\n"
            '{"action":"keep_monitoring"}\n\n'
            "Valid final actions:\n"
            "- keep_monitoring\n"
            "- infection_suspect\n"
            "- trigger_sepsis_alert"
        )
        user_payload = {
            "step_input": step_input,
            "history": history,
            "available_tools": available_tools,
        }
    user_prompt = json.dumps(user_payload, indent=2)
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _extract_json_object(text: str) -> dict[str, Any]:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError(f"Model did not return JSON: {text}")
        return json.loads(match.group(0))


def _build_repair_messages(
    step_input: dict[str, Any],
    history: list[dict[str, Any]],
    available_tools: list[str],
    bad_output: str,
) -> list[dict[str, str]]:
    messages = _build_messages(step_input, history, available_tools)
    messages.append({"role": "assistant", "content": bad_output})
    stay_id = int(step_input["stay_id"])
    t_hour = int(step_input["t_hour"])
    if _is_multitask_step(step_input):
        next_tool = _next_missing_tool(history, available_tools)
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
        repair_hint = (
            "Your previous reply was invalid because it was not exactly one JSON object. "
            "Respond again with JSON only and no extra text. "
            f'Use either {{"tool_name":"query_suspicion_of_infection","arguments":{{"stay_id":{stay_id},"t_hour":{t_hour}}}}} '
            'or {"action":"keep_monitoring"}.'
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
        if _is_multitask_step(step_input):
            return self._next_multitask_response(step_input, history, available_tools)
        return self._next_sepsis_response(step_input, history, available_tools)

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

        infection_output = self._latest_tool_output(history, stay_id, "has_suspected_infection")
        sofa_output = self._latest_tool_output(history, stay_id, "latest_sofa_24hours")

        if "query_suspicion_of_infection" in available_tools and "query_suspicion_of_infection" not in seen_tools:
            return ToolCall(
                tool_name="query_suspicion_of_infection",
                arguments={"stay_id": stay_id, "t_hour": t_hour},
            )
        if infection_output and infection_output.get("has_suspected_infection"):
            if "query_sofa" in available_tools and "query_sofa" not in seen_tools:
                return ToolCall(tool_name="query_sofa", arguments={"stay_id": stay_id, "t_hour": t_hour})
            latest_sofa = (sofa_output or {}).get("latest_sofa_24hours")
            if latest_sofa is not None and latest_sofa >= self.sofa_alert_threshold:
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


@dataclass(slots=True)
class QwenChatAgent:
    model: str = "Qwen/Qwen3.5-9B"
    temperature: float = 0.0
    top_p: float = 0.95
    max_new_tokens: int = 250
    repair_max_new_tokens: int = 120
    trace_callback: Callable[[dict[str, Any]], None] | None = field(default=None, repr=False)
    client: LocalQwenChat = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.client = LocalQwenChat(
            model_ref=self.model,
            temperature=self.temperature,
            top_p=self.top_p,
            max_new_tokens=self.max_new_tokens,
        )

    def next_response(
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
        next_tool = _next_missing_tool(history, available_tools) if _is_multitask_step(step_input) else None
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

        if next_tool is None and _is_multitask_step(step_input) and isinstance(response, ToolCall):
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
