from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from .schemas import ACTIONS, ActionDecision, ToolCall


class Agent(Protocol):
    def next_response(
        self,
        step_input: dict[str, Any],
        history: list[dict[str, Any]],
        available_tools: list[str],
    ) -> ToolCall | ActionDecision:
        ...


def _build_messages(
    step_input: dict[str, Any],
    history: list[dict[str, Any]],
    available_tools: list[str],
) -> list[dict[str, str]]:
    system_prompt = (
"""        You are an ICU rolling sepsis surveillance agent.

Task setting:
- This is a longitudinal monitoring task for one ICU stay.
- Monitoring happens once every 4 hours.
- The current checkpoint is given by t_hour, where t_hour is ICU-relative time such as 0, 4, 8, 12, 16, 20, 24.
- At each checkpoint, you may call tool then output one final action.
- Check infection first then check sofa. Sofa threshold for sepsis is 2. If both infection and sofa, then trigger sepsis. 

Available actions:
- keep_monitoring
- infection_suspect
- trigger_sepsis_alert

Action meanings:
- keep_monitoring: do not escalate yet.
- infection_suspect: suspected infection is already visible, but sepsis alert is not yet justified.
- trigger_sepsis_alert: suspected infection is visible and the visible SOFA evidence is sufficient to justify a sepsis alert.

Tool semantics:
1. query_suspicion_of_infection(stay_id, t_hour)
   - Returns whether suspected infection is visible by the current checkpoint.
   - Returns the first visible suspected infection time/hour and compact supporting evidence.
   - This is an infection event summary, not an hourly trend table.

2. query_sofa(stay_id, t_hour)
   - Returns the visible SOFA trajectory summary up to the current checkpoint.
   - Returns the latest visible SOFA, max SOFA so far, and recent trend/components.
   - This is support for organ dysfunction severity.

   
Output rules:
- Return exactly one JSON object.
- Return either a tool call OR a final action, not both.

Tool call format example:
{"tool_name":"query_suspicion_of_infection","arguments":{"stay_id":123,"t_hour":4}}


Final action format:
{"action":"keep_monitoring"}

Do not output any extra text before or after the JSON.
"""
    )
    user_prompt = json.dumps(
        {
            "step_input": step_input,
            "history": history,
            "available_tools": available_tools,
        },
        indent=2,
    )
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
    messages.append(
        {
            "role": "user",
            "content": (
                "Your previous reply was invalid because it was not exactly one JSON object. "
                "Respond again with JSON only and no extra text. "
                'Use either {"tool_name":"query_suspicion_of_infection","arguments":{"stay_id":123,"t_hour":0}} '
                'or {"action":"keep_monitoring"}.'
            ),
        }
    )
    return messages


def _coerce_agent_output(payload: dict[str, Any]) -> ToolCall | ActionDecision:
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

    def next_response(
        self,
        step_input: dict[str, Any],
        history: list[dict[str, Any]],
        available_tools: list[str],
    ) -> ToolCall | ActionDecision:
        t_hour = int(step_input["t_hour"])
        stay_id = int(step_input["stay_id"])
        seen_tools = {item["tool_name"] for item in history if item["type"] == "tool_call"}
        tool_outputs = [item["payload"] for item in history if item["type"] == "tool_output"]

        infection_output = next(
            (
                item
                for item in reversed(tool_outputs)
                if item.get("stay_id") == stay_id and "has_suspected_infection" in item
            ),
            None,
        )
        sofa_output = next(
            (
                item
                for item in reversed(tool_outputs)
                if item.get("stay_id") == stay_id and "latest_sofa_24hours" in item
            ),
            None,
        )

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
            raise RuntimeError(
                "Running the local Qwen agent requires 'torch' to be installed."
            ) from exc

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
            raise RuntimeError(
                "Running the local Qwen agent requires 'transformers' to be installed."
            ) from exc

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
            prompt = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
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
        messages = _build_messages(step_input, history, available_tools)
        content = self.client.generate(messages)
        try:
            return _coerce_agent_output(_extract_json_object(content))
        except (ValueError, json.JSONDecodeError):
            original_max_tokens = self.client.max_new_tokens
            repair_messages = _build_repair_messages(step_input, history, available_tools, content)
            self.client.max_new_tokens = self.repair_max_new_tokens
            try:
                repaired = self.client.generate(repair_messages)
            finally:
                self.client.max_new_tokens = original_max_tokens
            return _coerce_agent_output(_extract_json_object(repaired))
