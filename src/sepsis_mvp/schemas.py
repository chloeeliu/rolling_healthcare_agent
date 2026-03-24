from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


ACTIONS = (
    "keep_monitoring",
    "infection_suspect",
    "trigger_sepsis_alert",
)


@dataclass(slots=True)
class Checkpoint:
    t_hour: int
    state_label: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Trajectory:
    trajectory_id: str
    stay_id: int
    subject_id: int
    hadm_id: int
    anchor: str
    step_hours: int
    horizon_hours: int
    transitions: dict[str, int | None]
    checkpoints: list[Checkpoint]
    icu_intime: str | None = None
    icu_outtime: str | None = None
    icu_los_hours: float | None = None
    is_sepsis: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["checkpoints"] = [checkpoint.to_dict() for checkpoint in self.checkpoints]
        return payload


@dataclass(slots=True)
class ICUStay:
    stay_id: int
    subject_id: int
    hadm_id: int
    icu_intime: datetime


@dataclass(slots=True)
class SuspicionOfInfectionRow:
    stay_id: int
    suspected_infection_time: datetime
    antibiotic: str | None = None
    antibiotic_time: datetime | None = None
    culture_time: datetime | None = None
    specimen: str | None = None
    positive_culture: int | None = None


@dataclass(slots=True)
class Sepsis3Row:
    stay_id: int
    sepsis_time: datetime


@dataclass(slots=True)
class SofaRow:
    stay_id: int
    hr: int
    sofa_24hours: int
    respiration_24hours: int | None = None
    coagulation_24hours: int | None = None
    liver_24hours: int | None = None
    cardiovascular_24hours: int | None = None
    cns_24hours: int | None = None
    renal_24hours: int | None = None

    def components(self) -> dict[str, int | None]:
        return {
            "respiration_24hours": self.respiration_24hours,
            "coagulation_24hours": self.coagulation_24hours,
            "liver_24hours": self.liver_24hours,
            "cardiovascular_24hours": self.cardiovascular_24hours,
            "cns_24hours": self.cns_24hours,
            "renal_24hours": self.renal_24hours,
        }


@dataclass(slots=True)
class AgentStepInput:
    trajectory_id: str
    stay_id: int
    step_index: int
    t_hour: int
    available_tools: list[str]
    instruction: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ToolCall:
    tool_name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class ActionDecision:
    action: str


@dataclass(slots=True)
class StepRecord:
    step_index: int
    t_hour: int
    gt_action: str
    predicted_action: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_outputs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TrajectoryRollout:
    trajectory_id: str
    stay_id: int
    steps: list[StepRecord]
    first_predicted_infection_hour: int | None
    first_predicted_alert_hour: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
