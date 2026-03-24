from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Any

import duckdb

from .schemas import ICUStay, SofaRow, SuspicionOfInfectionRow


class ConceptToolRuntime:
    def __init__(self, concept_tables: dict[str, list[Any]]):
        self.stays: dict[int, ICUStay] = {stay.stay_id: stay for stay in concept_tables["icustays"]}
        self.suspicion_rows: dict[int, list[SuspicionOfInfectionRow]] = defaultdict(list)
        self.sofa_rows: dict[int, list[SofaRow]] = defaultdict(list)
        for row in concept_tables.get("suspicion_of_infection", []):
            self.suspicion_rows[row.stay_id].append(row)
        for row in concept_tables.get("sofa", []):
            self.sofa_rows[row.stay_id].append(row)
        for stay_rows in self.suspicion_rows.values():
            stay_rows.sort(key=lambda row: row.suspected_infection_time)
        for stay_rows in self.sofa_rows.values():
            stay_rows.sort(key=lambda row: row.hr)

    def _visible_until(self, stay_id: int, t_hour: int):
        stay = self.stays[stay_id]
        return stay.icu_intime + timedelta(hours=t_hour)

    def query_suspicion_of_infection(self, stay_id: int, t_hour: int) -> dict[str, Any]:
        visible_until = self._visible_until(stay_id, t_hour)
        visible_rows = [
            row
            for row in self.suspicion_rows.get(stay_id, [])
            if row.suspected_infection_time <= visible_until
        ]
        if not visible_rows:
            return {
                "stay_id": stay_id,
                "t_hour": t_hour,
                "has_suspected_infection": False,
                "first_visible_suspected_infection_hour": None,
                "first_visible_suspected_infection_time": None,
                "evidence": [],
            }

        first = visible_rows[0]
        anchor = self.stays[stay_id].icu_intime
        first_hour = round((first.suspected_infection_time - anchor).total_seconds() / 3600.0, 2)
        evidence = []
        for row in visible_rows:
            evidence.append(
                {
                    "antibiotic": row.antibiotic,
                    "antibiotic_time": row.antibiotic_time.isoformat() if row.antibiotic_time else None,
                    "culture_time": row.culture_time.isoformat() if row.culture_time else None,
                    "specimen": row.specimen,
                    "positive_culture": row.positive_culture,
                }
            )
        return {
            "stay_id": stay_id,
            "t_hour": t_hour,
            "has_suspected_infection": True,
            "first_visible_suspected_infection_hour": first_hour,
            "first_visible_suspected_infection_time": first.suspected_infection_time.isoformat(),
            "evidence": evidence,
        }

    def query_sofa(self, stay_id: int, t_hour: int) -> dict[str, Any]:
        visible_rows = [row for row in self.sofa_rows.get(stay_id, []) if row.hr <= t_hour]
        if not visible_rows:
            return {
                "stay_id": stay_id,
                "t_hour": t_hour,
                "latest_visible_hr": None,
                "latest_sofa_24hours": None,
                "max_sofa_24hours_so_far": None,
                "latest_components": {},
            }

        latest = visible_rows[-1]
        max_sofa = max(row.sofa_24hours for row in visible_rows)
        return {
            "stay_id": stay_id,
            "t_hour": t_hour,
            "latest_visible_hr": latest.hr,
            "latest_sofa_24hours": latest.sofa_24hours,
            "max_sofa_24hours_so_far": max_sofa,
            "latest_components": latest.components(),
        }

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "query_suspicion_of_infection":
            return self.query_suspicion_of_infection(**arguments)
        if tool_name == "query_sofa":
            return self.query_sofa(**arguments)
        raise ValueError(f"Unknown tool: {tool_name}")


class DuckDBConceptToolRuntime:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.connection = duckdb.connect(db_path, read_only=True)
        self._validate_required_tables()

    def _validate_required_tables(self) -> None:
        required = {
            "mimiciv_icu.icustays",
            "mimiciv_derived.suspicion_of_infection",
            "mimiciv_derived.sofa",
        }
        rows = self.connection.execute(
            """
            SELECT table_schema || '.' || table_name AS full_name
            FROM information_schema.tables
            """
        ).fetchall()
        available = {row[0] for row in rows}
        missing = sorted(required - available)
        if missing:
            raise RuntimeError(
                "Missing required DuckDB relations for the MVP tool layer: "
                + ", ".join(missing)
            )

    def _visible_until(self, stay_id: int, t_hour: int):
        row = self.connection.execute(
            """
            SELECT intime
            FROM mimiciv_icu.icustays
            WHERE stay_id = ?
            """,
            [stay_id],
        ).fetchone()
        if row is None:
            raise ValueError(f"stay_id {stay_id} not found in mimiciv_icu.icustays")
        return row[0] + timedelta(hours=t_hour)

    def query_suspicion_of_infection(self, stay_id: int, t_hour: int) -> dict[str, Any]:
        visible_until = self._visible_until(stay_id, t_hour)
        rows = self.connection.execute(
            """
            SELECT
                antibiotic,
                antibiotic_time,
                suspected_infection_time,
                culture_time,
                specimen,
                positive_culture
            FROM mimiciv_derived.suspicion_of_infection
            WHERE stay_id = ?
              AND suspected_infection = 1
              AND suspected_infection_time IS NOT NULL
              AND suspected_infection_time <= ?
            ORDER BY suspected_infection_time, antibiotic_time
            """,
            [stay_id, visible_until],
        ).fetchall()
        if not rows:
            return {
                "stay_id": stay_id,
                "t_hour": t_hour,
                "has_suspected_infection": False,
                "first_visible_suspected_infection_hour": None,
                "first_visible_suspected_infection_time": None,
                "evidence": [],
            }

        first = rows[0]
        intime = self._visible_until(stay_id, 0)
        first_hour = round((first[2] - intime).total_seconds() / 3600.0, 2)
        evidence = [
            {
                "antibiotic": antibiotic,
                "antibiotic_time": antibiotic_time.isoformat() if antibiotic_time else None,
                "culture_time": culture_time.isoformat() if culture_time else None,
                "specimen": specimen,
                "positive_culture": positive_culture,
            }
            for antibiotic, antibiotic_time, _, culture_time, specimen, positive_culture in rows
        ]
        return {
            "stay_id": stay_id,
            "t_hour": t_hour,
            "has_suspected_infection": True,
            "first_visible_suspected_infection_hour": first_hour,
            "first_visible_suspected_infection_time": first[2].isoformat(),
            "evidence": evidence,
        }

    def query_sofa(self, stay_id: int, t_hour: int) -> dict[str, Any]:
        latest = self.connection.execute(
            """
            SELECT
                hr,
                sofa_24hours,
                respiration_24hours,
                coagulation_24hours,
                liver_24hours,
                cardiovascular_24hours,
                cns_24hours,
                renal_24hours
            FROM mimiciv_derived.sofa
            WHERE stay_id = ?
              AND hr <= ?
            ORDER BY hr DESC
            LIMIT 1
            """,
            [stay_id, t_hour],
        ).fetchone()
        if latest is None:
            return {
                "stay_id": stay_id,
                "t_hour": t_hour,
                "latest_visible_hr": None,
                "latest_sofa_24hours": None,
                "max_sofa_24hours_so_far": None,
                "latest_components": {},
            }

        max_sofa = self.connection.execute(
            """
            SELECT MAX(sofa_24hours)
            FROM mimiciv_derived.sofa
            WHERE stay_id = ?
              AND hr <= ?
            """,
            [stay_id, t_hour],
        ).fetchone()[0]
        return {
            "stay_id": stay_id,
            "t_hour": t_hour,
            "latest_visible_hr": int(latest[0]),
            "latest_sofa_24hours": latest[1],
            "max_sofa_24hours_so_far": max_sofa,
            "latest_components": {
                "respiration_24hours": latest[2],
                "coagulation_24hours": latest[3],
                "liver_24hours": latest[4],
                "cardiovascular_24hours": latest[5],
                "cns_24hours": latest[6],
                "renal_24hours": latest[7],
            },
        }

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "query_suspicion_of_infection":
            return self.query_suspicion_of_infection(**arguments)
        if tool_name == "query_sofa":
            return self.query_sofa(**arguments)
        raise ValueError(f"Unknown tool: {tool_name}")
