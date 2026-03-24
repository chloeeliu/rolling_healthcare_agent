from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
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


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError(f"Model did not return JSON: {text}")
        return json.loads(match.group(0))


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
class QwenChatAgent:
    model: str = "qwen3.5"
    base_url: str | None = None
    api_key: str | None = None
    temperature: float = 0.0
    max_tokens: int = 250
    timeout_seconds: int = 60

    def __post_init__(self) -> None:
        if self.base_url is None:
            self.base_url = os.environ.get("QWEN_BASE_URL")
        if self.api_key is None:
            self.api_key = os.environ.get("QWEN_API_KEY")
        self.model = os.environ.get("QWEN_MODEL", self.model)

    def _request_payload(
        self,
        step_input: dict[str, Any],
        history: list[dict[str, Any]],
        available_tools: list[str],
    ) -> dict[str, Any]:
        system_prompt = (
            "You are a sepsis surveillance agent. "
            "Use tools only from the allowed list. "
            "Return exactly one JSON object. "
            "If you need a tool, return "
            '{"tool_name":"query_sofa","arguments":{"stay_id":123,"t_hour":4}}. '
            "If you are ready to decide, return "
            '{"action":"keep_monitoring"} with one of: '
            "keep_monitoring, infection_suspect, trigger_sepsis_alert."
        )
        user_prompt = json.dumps(
            {
                "step_input": step_input,
                "history": history,
                "available_tools": available_tools,
            },
            indent=2,
        )
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

    def _chat_completion(self, payload: dict[str, Any]) -> str:
        if not self.base_url or not self.api_key:
            raise RuntimeError("QWEN_BASE_URL and QWEN_API_KEY must be set for the Qwen agent.")
        request = urllib.request.Request(
            self.base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Qwen endpoint returned HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Could not reach Qwen endpoint: {exc}") from exc

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected Qwen response payload: {data}") from exc

    def next_response(
        self,
        step_input: dict[str, Any],
        history: list[dict[str, Any]],
        available_tools: list[str],
    ) -> ToolCall | ActionDecision:
        payload = self._request_payload(step_input, history, available_tools)
        content = self._chat_completion(payload)
        return _coerce_agent_output(_extract_json_object(content))

