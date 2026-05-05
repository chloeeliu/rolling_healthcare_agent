from __future__ import annotations

import builtins
from typing import Any

_original_import = builtins.__import__
_patched_sglang_http_server = False


def _patch_sglang_http_server(module: Any) -> None:
    global _patched_sglang_http_server
    if _patched_sglang_http_server or hasattr(module, "_launch_subprocesses"):
        _patched_sglang_http_server = True
        return
    try:
        from sglang.srt.entrypoints.engine import Engine
    except Exception:
        return

    def _launch_subprocesses(*args: Any, **kwargs: Any):
        return Engine._launch_subprocesses(*args, **kwargs)

    module._launch_subprocesses = _launch_subprocesses
    _patched_sglang_http_server = True


def _import_with_sglang_compat(name: str, globals=None, locals=None, fromlist=(), level: int = 0):
    module = _original_import(name, globals, locals, fromlist, level)
    target_name = "sglang.srt.entrypoints.http_server"
    if name == target_name or (name == "sglang.srt.entrypoints" and "http_server" in fromlist):
        try:
            import sglang.srt.entrypoints.http_server as http_server
        except Exception:
            return module
        _patch_sglang_http_server(http_server)
    return module


builtins.__import__ = _import_with_sglang_compat
