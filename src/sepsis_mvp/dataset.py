from __future__ import annotations

import csv
import json
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .schemas import Checkpoint, ICUStay, Sepsis3Row, SofaRow, SuspicionOfInfectionRow, Trajectory


MVP_ACTIONS = {
    "keep_monitoring",
    "infection_suspect",
    "trigger_sepsis_alert",
}


@dataclass(slots=True)
class CSVLoadResult:
    trajectories: list[Trajectory]
    included_trajectories: int
    skipped_trajectories: int
    skipped_reasons: dict[str, int]


def parse_datetime(value: str | None) -> datetime | None:
    if value in (None, ""):
        return None
    return datetime.fromisoformat(value)


def load_concept_tables(path: str | Path) -> dict[str, list[Any]]:
    data = json.loads(Path(path).read_text())
    icustays = [
        ICUStay(
            stay_id=int(row["stay_id"]),
            subject_id=int(row["subject_id"]),
            hadm_id=int(row["hadm_id"]),
            icu_intime=parse_datetime(row["icu_intime"]),
        )
        for row in data["icustays"]
    ]
    suspicion = [
        SuspicionOfInfectionRow(
            stay_id=int(row["stay_id"]),
            suspected_infection_time=parse_datetime(row["suspected_infection_time"]),
            antibiotic=row.get("antibiotic"),
            antibiotic_time=parse_datetime(row.get("antibiotic_time")),
            culture_time=parse_datetime(row.get("culture_time")),
            specimen=row.get("specimen"),
            positive_culture=row.get("positive_culture"),
        )
        for row in data.get("suspicion_of_infection", [])
    ]
    sepsis = [
        Sepsis3Row(
            stay_id=int(row["stay_id"]),
            sepsis_time=parse_datetime(row["sepsis_time"]),
        )
        for row in data.get("sepsis3", [])
    ]
    sofa = [
        SofaRow(
            stay_id=int(row["stay_id"]),
            hr=int(row["hr"]),
            sofa_24hours=int(row["sofa_24hours"]),
            respiration_24hours=row.get("respiration_24hours"),
            coagulation_24hours=row.get("coagulation_24hours"),
            liver_24hours=row.get("liver_24hours"),
            cardiovascular_24hours=row.get("cardiovascular_24hours"),
            cns_24hours=row.get("cns_24hours"),
            renal_24hours=row.get("renal_24hours"),
        )
        for row in data.get("sofa", [])
    ]
    return {
        "icustays": icustays,
        "suspicion_of_infection": suspicion,
        "sepsis3": sepsis,
        "sofa": sofa,
    }


def save_trajectories(trajectories: list[Trajectory], path: str | Path) -> None:
    payload = [trajectory.to_dict() for trajectory in trajectories]
    Path(path).write_text(json.dumps(payload, indent=2))


def load_trajectories(path: str | Path) -> list[Trajectory]:
    raw = json.loads(Path(path).read_text())
    trajectories = []
    for item in raw:
        trajectories.append(
            Trajectory(
                trajectory_id=item["trajectory_id"],
                stay_id=int(item["stay_id"]),
                subject_id=int(item["subject_id"]),
                hadm_id=int(item["hadm_id"]),
                anchor=item["anchor"],
                step_hours=int(item["step_hours"]),
                horizon_hours=int(item["horizon_hours"]),
                transitions=item["transitions"],
                checkpoints=[Checkpoint(**checkpoint) for checkpoint in item["checkpoints"]],
                icu_intime=item.get("icu_intime"),
                icu_outtime=item.get("icu_outtime"),
                icu_los_hours=item.get("icu_los_hours"),
                is_sepsis=item.get("is_sepsis"),
            )
        )
    return trajectories


def _parse_optional_int(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    return int(float(value))


def _parse_optional_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _parse_bool(value: str | None) -> bool | None:
    if value in (None, ""):
        return None
    return value.strip().lower() == "true" or value.strip() == "1"


def _trajectory_skip_reason(rows: list[dict[str, str]]) -> str | None:
    labels = {row["state_label"] for row in rows}
    if not labels.issubset(MVP_ACTIONS):
        return "unsupported_labels"

    first = rows[0]
    infection_start_hour = _parse_optional_int(first.get("infection_start_hour"))
    sepsis_start_hour = _parse_optional_int(first.get("sepsis_start_hour"))
    if (
        infection_start_hour is not None
        and sepsis_start_hour is not None
        and infection_start_hour > sepsis_start_hour
    ):
        return "infection_after_sepsis"
    return None


def load_rolling_csv_dataset(
    path: str | Path,
    *,
    strict_mvp: bool = True,
) -> CSVLoadResult:
    grouped_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    with Path(path).open() as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            grouped_rows[row["trajectory_id"]].append(row)

    trajectories: list[Trajectory] = []
    skipped_reasons: dict[str, int] = defaultdict(int)

    for trajectory_id, rows in sorted(grouped_rows.items()):
        rows.sort(key=lambda row: int(row["t_hour"]))
        if strict_mvp:
            reason = _trajectory_skip_reason(rows)
            if reason is not None:
                skipped_reasons[reason] += 1
                continue

        first = rows[0]
        checkpoints = [
            Checkpoint(
                t_hour=int(row["t_hour"]),
                state_label=row["state_label"],
            )
            for row in rows
        ]
        step_hours = checkpoints[1].t_hour - checkpoints[0].t_hour if len(checkpoints) > 1 else 4
        horizon_hours = checkpoints[-1].t_hour

        trajectories.append(
            Trajectory(
                trajectory_id=trajectory_id,
                stay_id=int(first["stay_id"]),
                subject_id=int(first["subject_id"]),
                hadm_id=int(first["hadm_id"]),
                anchor="icu_intime",
                step_hours=step_hours,
                horizon_hours=horizon_hours,
                transitions={
                    "infection_start_hour": _parse_optional_int(first.get("infection_start_hour")),
                    "organ_dysfunction_start_hour": _parse_optional_int(first.get("organ_dysfunction_start_hour")),
                    "sepsis_start_hour": _parse_optional_int(first.get("sepsis_start_hour")),
                    "infection_start_time": first.get("infection_start_time") or None,
                    "organ_dysfunction_start_time": first.get("organ_dysfunction_start_time") or None,
                    "sepsis_start_time": first.get("sepsis_start_time") or None,
                },
                checkpoints=checkpoints,
                icu_intime=first.get("icu_intime") or None,
                icu_outtime=first.get("icu_outtime") or None,
                icu_los_hours=_parse_optional_float(first.get("icu_los_hours")),
                is_sepsis=_parse_bool(first.get("is_sepsis")),
            )
        )

    return CSVLoadResult(
        trajectories=trajectories,
        included_trajectories=len(trajectories),
        skipped_trajectories=sum(skipped_reasons.values()),
        skipped_reasons=dict(skipped_reasons),
    )


def hour_offset(anchor: datetime, event_time: datetime | None) -> float | None:
    if event_time is None:
        return None
    return (event_time - anchor).total_seconds() / 3600.0


def checkpoint_hour_for_event(event_hour: float | None, step_hours: int, horizon_hours: int) -> int | None:
    if event_hour is None:
        return None
    snapped = int(math.ceil(max(0.0, event_hour) / step_hours) * step_hours)
    return min(snapped, horizon_hours)


def label_for_checkpoint(
    checkpoint_hour: int,
    infection_start_hour: int | None,
    sepsis_start_hour: int | None,
) -> str:
    if infection_start_hour is None or checkpoint_hour < infection_start_hour:
        return "keep_monitoring"
    if sepsis_start_hour is None or checkpoint_hour < sepsis_start_hour:
        return "infection_suspect"
    return "trigger_sepsis_alert"


def build_dataset(
    concept_tables: dict[str, list[Any]],
    *,
    step_hours: int = 4,
    horizon_hours: int = 24,
    sample_sepsis: int | None = None,
    sample_non_sepsis: int | None = None,
    seed: int = 7,
) -> list[Trajectory]:
    stays = {row.stay_id: row for row in concept_tables["icustays"]}
    suspicion_by_stay: dict[int, list[SuspicionOfInfectionRow]] = defaultdict(list)
    for row in concept_tables["suspicion_of_infection"]:
        suspicion_by_stay[row.stay_id].append(row)
    sepsis_by_stay: dict[int, list[Sepsis3Row]] = defaultdict(list)
    for row in concept_tables["sepsis3"]:
        sepsis_by_stay[row.stay_id].append(row)

    sepsis_stay_ids = sorted(sepsis_by_stay.keys())
    non_sepsis_stay_ids = sorted(stay_id for stay_id in stays if stay_id not in sepsis_by_stay)

    rng = random.Random(seed)
    if sample_sepsis is not None and sample_sepsis < len(sepsis_stay_ids):
        sepsis_stay_ids = sorted(rng.sample(sepsis_stay_ids, sample_sepsis))
    if sample_non_sepsis is not None and sample_non_sepsis < len(non_sepsis_stay_ids):
        non_sepsis_stay_ids = sorted(rng.sample(non_sepsis_stay_ids, sample_non_sepsis))

    selected_stay_ids = sepsis_stay_ids + non_sepsis_stay_ids
    trajectories: list[Trajectory] = []

    for stay_id in selected_stay_ids:
        stay = stays[stay_id]
        suspicion_rows = sorted(
            suspicion_by_stay.get(stay_id, []),
            key=lambda row: row.suspected_infection_time,
        )
        sepsis_rows = sorted(sepsis_by_stay.get(stay_id, []), key=lambda row: row.sepsis_time)

        first_suspicion_time = suspicion_rows[0].suspected_infection_time if suspicion_rows else None
        first_sepsis_time = sepsis_rows[0].sepsis_time if sepsis_rows else None

        infection_start_hour = checkpoint_hour_for_event(
            hour_offset(stay.icu_intime, first_suspicion_time),
            step_hours,
            horizon_hours,
        )
        sepsis_start_hour = checkpoint_hour_for_event(
            hour_offset(stay.icu_intime, first_sepsis_time),
            step_hours,
            horizon_hours,
        )

        checkpoints = []
        for t_hour in range(0, horizon_hours + 1, step_hours):
            checkpoints.append(
                Checkpoint(
                    t_hour=t_hour,
                    state_label=label_for_checkpoint(t_hour, infection_start_hour, sepsis_start_hour),
                )
            )

        trajectories.append(
            Trajectory(
                trajectory_id=f"mimiciv_stay_{stay_id}",
                stay_id=stay.stay_id,
                subject_id=stay.subject_id,
                hadm_id=stay.hadm_id,
                anchor="icu_intime",
                step_hours=step_hours,
                horizon_hours=horizon_hours,
                transitions={
                    "infection_start_hour": infection_start_hour,
                    "sepsis_start_hour": sepsis_start_hour,
                },
                checkpoints=checkpoints,
            )
        )

    return sorted(trajectories, key=lambda trajectory: trajectory.stay_id)
