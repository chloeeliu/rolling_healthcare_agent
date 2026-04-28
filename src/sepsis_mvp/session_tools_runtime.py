from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Union
from uuid import uuid4

from .duckdb_session import DuckDBCodeSession


@dataclass(slots=True)
class _StayContext:
    stay_id: int
    subject_id: int
    hadm_id: int
    intime: Any
    visible_until: Any


@dataclass(slots=True)
class _ToolSession:
    context: _StayContext
    session: DuckDBCodeSession
    loaded_files: set[str]


class SessionToolsDuckDBRuntime:
    TOOL_NAMES = {
        "search_guidelines",
        "get_guideline",
        "search_functions",
        "get_function_info",
        "load_function",
        "call_function",
    }

    def __init__(
        self,
        db_path: str | Path,
        *,
        guidelines_dir: str | Path | None = None,
        functions_dir: str | Path | None = None,
        session_profile: str = "surveillance",
    ) -> None:
        try:
            import duckdb
        except ImportError as exc:
            raise RuntimeError("Session-tools backend requires the 'duckdb' package.") from exc
        try:
            import pandas as pd
        except ImportError as exc:
            raise RuntimeError("Session-tools backend requires the 'pandas' package.") from exc

        self.duckdb = duckdb
        self.pd = pd
        self.db_path = str(db_path)
        self.guidelines_dir = str(guidelines_dir) if guidelines_dir is not None else None
        self.functions_dir = str(functions_dir) if functions_dir is not None else None
        self.session_profile = session_profile
        self.connection = duckdb.connect(self.db_path, read_only=True)
        self._sessions: dict[str, _ToolSession] = {}
        self._file_exports, self._function_to_files = self._build_function_index()

    def _build_function_index(self) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        file_exports: dict[str, list[str]] = {}
        function_to_files: dict[str, list[str]] = {}
        if not self.functions_dir:
            return file_exports, function_to_files
        root = Path(self.functions_dir)
        if not root.is_dir():
            return file_exports, function_to_files
        for path in sorted(root.glob("*.py")):
            try:
                tree = ast.parse(path.read_text())
            except Exception:
                continue
            exported: list[str] = []
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                    exported.append(node.name)
            file_name = path.stem
            file_exports[file_name] = exported
            for fn_name in exported:
                function_to_files.setdefault(fn_name, []).append(file_name)
        return file_exports, function_to_files

    def _recommended_entrypoints(self, file_name: str) -> list[str]:
        exported = self._file_exports.get(file_name, [])
        if not exported:
            return []
        if file_name in exported:
            return [file_name]
        return exported[:1]

    def _stay_context(self, stay_id: int, t_hour: int) -> _StayContext:
        row = self.connection.execute(
            """
            SELECT stay_id, subject_id, hadm_id, intime
            FROM mimiciv_icu.icustays
            WHERE stay_id = ?
            """,
            [stay_id],
        ).fetchone()
        if row is None:
            raise ValueError(f"stay_id {stay_id} not found in mimiciv_icu.icustays")
        visible_until = row[3] + timedelta(hours=t_hour)
        return _StayContext(
            stay_id=int(row[0]),
            subject_id=int(row[1]),
            hadm_id=int(row[2]),
            intime=row[3],
            visible_until=visible_until,
        )

    def _create_session(self, context: _StayContext) -> DuckDBCodeSession:
        allowed_relations = None if self.session_profile == "surveillance" else None
        session = DuckDBCodeSession(
            db_path=self.db_path,
            subject_id=context.subject_id,
            hadm_id=context.hadm_id,
            stay_id=context.stay_id,
            visible_until=context.visible_until,
            time_bounded_views=True,
            allowed_relations=allowed_relations,
            guidelines_dir=self.guidelines_dir,
            functions_dir=self.functions_dir,
        )
        session.namespace["Union"] = Union
        return session

    def start_step_session(self, *, stay_id: int, t_hour: int) -> str:
        context = self._stay_context(stay_id, t_hour)
        session_id = str(uuid4())
        self._sessions[session_id] = _ToolSession(
            context=context,
            session=self._create_session(context),
            loaded_files=set(),
        )
        return session_id

    def close_step_session(self, session_id: str | None) -> None:
        if session_id is None:
            return
        session = self._sessions.pop(session_id, None)
        if session is not None:
            session.session.close()

    def _require_session(self, session_id: str | None) -> _ToolSession:
        if not session_id or session_id not in self._sessions:
            raise ValueError("session_tools backend requires a valid session_id.")
        return self._sessions[session_id]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool_name not in self.TOOL_NAMES:
            raise ValueError(f"Unknown tool: {tool_name}")
        tool_session = self._require_session(arguments.get("session_id"))
        runtime_session = tool_session.session
        if tool_name == "search_guidelines":
            keyword = str(arguments.get("keyword", ""))
            helper = runtime_session.namespace["search_guidelines"]
            matches = helper(keyword)
            return {"ok": True, "tool_name": tool_name, "keyword": keyword, "matches": self._json_safe(matches)}
        if tool_name == "get_guideline":
            name = str(arguments["name"])
            helper = runtime_session.namespace["get_guideline"]
            text = helper(name)
            return {"ok": True, "tool_name": tool_name, "name": name, "text": text}
        if tool_name == "search_functions":
            keyword = str(arguments.get("keyword", ""))
            helper = runtime_session.namespace["search_functions"]
            matches = helper(keyword)
            return {"ok": True, "tool_name": tool_name, "keyword": keyword, "matches": self._json_safe(matches)}
        if tool_name == "get_function_info":
            file_name = str(arguments["name"])
            helper = runtime_session.namespace["get_function_info"]
            summary = helper(file_name)
            return {
                "ok": True,
                "tool_name": tool_name,
                "file": file_name,
                "exported_functions": list(self._file_exports.get(file_name, [])),
                "recommended_entrypoints": self._recommended_entrypoints(file_name),
                "summary": summary,
            }
        if tool_name == "load_function":
            file_name = str(arguments["name"])
            loaded, message = self._load_library_file(tool_session, file_name)
            return {
                "ok": loaded,
                "tool_name": tool_name,
                "file": file_name,
                "message": message,
                "exported_functions": list(self._file_exports.get(file_name, [])),
                "recommended_entrypoints": self._recommended_entrypoints(file_name),
            }
        if tool_name == "call_function":
            return self._call_function(tool_session, arguments)
        raise ValueError(f"Unknown tool: {tool_name}")

    def _call_function(self, tool_session: _ToolSession, arguments: dict[str, Any]) -> dict[str, Any]:
        runtime_session = tool_session.session
        function_name = str(arguments["function_name"])
        call_arguments = arguments.get("arguments", {})
        if not isinstance(call_arguments, dict):
            raise ValueError("call_function.arguments must be a JSON object of keyword arguments.")
        auto_loaded_file: str | None = None
        if function_name not in runtime_session.namespace:
            owner_files = self._function_to_files.get(function_name, [])
            if not owner_files:
                return {
                    "ok": False,
                    "tool_name": "call_function",
                    "function_name": function_name,
                    "error_type": "UnknownFunction",
                    "error_message": f"Function '{function_name}' was not found in indexed library exports.",
                }
            if len(owner_files) > 1:
                return {
                    "ok": False,
                    "tool_name": "call_function",
                    "function_name": function_name,
                    "error_type": "AmbiguousFunction",
                    "error_message": f"Function '{function_name}' is exported by multiple files: {owner_files}.",
                    "owner_files": owner_files,
                }
            auto_loaded_file = owner_files[0]
            loaded, load_message = self._load_library_file(tool_session, auto_loaded_file)
            if not loaded:
                return {
                    "ok": False,
                    "tool_name": "call_function",
                    "function_name": function_name,
                    "error_type": "LoadResolutionError",
                    "error_message": (
                        f"File '{auto_loaded_file}' could not be loaded before calling '{function_name}'."
                    ),
                    "load_message": load_message,
                }
            if function_name not in runtime_session.namespace:
                return {
                    "ok": False,
                    "tool_name": "call_function",
                    "function_name": function_name,
                    "error_type": "LoadResolutionError",
                    "error_message": (
                        f"File '{auto_loaded_file}' loaded but '{function_name}' is not available in session namespace."
                    ),
                    "load_message": load_message,
                }
        fn = runtime_session.namespace.get(function_name)
        if not callable(fn):
            return {
                "ok": False,
                "tool_name": "call_function",
                "function_name": function_name,
                "error_type": "NotCallable",
                "error_message": f"Object '{function_name}' exists in session namespace but is not callable.",
            }
        try:
            result = fn(**call_arguments)
        except Exception as exc:
            return {
                "ok": False,
                "tool_name": "call_function",
                "function_name": function_name,
                "auto_loaded_file": auto_loaded_file,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "query_stats": runtime_session.get_query_stats(),
            }
        return {
            "ok": True,
            "tool_name": "call_function",
            "function_name": function_name,
            "auto_loaded_file": auto_loaded_file,
            "result": self._summarize_result(result),
            "query_stats": runtime_session.get_query_stats(),
        }

    def _load_library_file(self, tool_session: _ToolSession, file_name: str) -> tuple[bool, str]:
        if file_name in tool_session.loaded_files:
            return True, f"Functions from '{file_name}' already loaded in this checkpoint session."
        path = self._function_file_path(file_name)
        if path is None:
            return False, f"(no saved function found for '{file_name}')"
        try:
            source = path.read_text()
        except Exception as exc:
            return False, f"Error reading functions from '{file_name}': {exc}"
        try:
            compiled = self._compile_library_source(source, file_name=file_name)
            exec(compiled, tool_session.session.namespace)
        except Exception as exc:
            return False, f"Error loading functions from '{file_name}': {exc}"
        tool_session.loaded_files.add(file_name)
        return True, f"Functions from '{file_name}' loaded successfully."

    def _function_file_path(self, file_name: str) -> Path | None:
        if not self.functions_dir:
            return None
        path = Path(self.functions_dir) / f"{file_name}.py"
        if not path.is_file():
            return None
        return path

    def _compile_library_source(self, source: str, *, file_name: str) -> Any:
        tree = ast.parse(source, filename=f"{file_name}.py")
        filtered_body: list[ast.stmt] = []
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            filtered_body.append(node)
        module = ast.Module(body=filtered_body, type_ignores=getattr(tree, "type_ignores", []))
        ast.fix_missing_locations(module)
        return compile(module, filename=f"{file_name}.py", mode="exec")

    def _summarize_result(self, value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        if isinstance(value, self.pd.DataFrame):
            preview = value.head(5).copy()
            preview = preview.where(self.pd.notnull(preview), None)
            return {
                "kind": "dataframe",
                "rows": int(len(value)),
                "columns": [str(col) for col in value.columns.tolist()],
                "head": self._json_safe(preview.to_dict(orient="records")),
            }
        if isinstance(value, self.pd.Series):
            preview = value.head(10).copy()
            preview = preview.where(self.pd.notnull(preview), None)
            return {
                "kind": "series",
                "length": int(len(value)),
                "head": self._json_safe(preview.to_dict()),
            }
        if isinstance(value, (list, tuple)):
            preview = list(value[:10])
            return {"kind": type(value).__name__, "length": len(value), "preview": self._json_safe(preview)}
        if isinstance(value, dict):
            preview = {str(key): value[key] for key in list(value)[:10]}
            return {"kind": "dict", "preview": self._json_safe(preview)}
        return {"kind": type(value).__name__, "repr": self._truncate(repr(value), limit=1500)}

    def _json_safe(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, self.pd.DataFrame):
            preview = value.head(5).copy()
            preview = preview.where(self.pd.notnull(preview), None)
            return {
                "kind": "dataframe",
                "rows": int(len(value)),
                "columns": [str(col) for col in value.columns.tolist()],
                "head": self._json_safe(preview.to_dict(orient="records")),
            }
        if isinstance(value, self.pd.Series):
            preview = value.head(10).copy()
            preview = preview.where(self.pd.notnull(preview), None)
            return {
                "kind": "series",
                "length": int(len(value)),
                "head": self._json_safe(preview.to_dict()),
            }
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._json_safe(item) for item in value]
        if hasattr(value, "item"):
            try:
                return self._json_safe(value.item())
            except Exception:
                pass
        if hasattr(value, "isoformat"):
            try:
                return value.isoformat()
            except Exception:
                pass
        try:
            if bool(self.pd.isna(value)):
                return None
        except Exception:
            pass
        return self._truncate(repr(value), limit=500)

    def _truncate(self, text: str | None, *, limit: int = 3000) -> str:
        if not text:
            return ""
        if len(text) <= limit:
            return text
        return text[: limit - 15] + "\n...[truncated]"
