"""The MCP boundary: every tool call runs here, and every input file is confined here."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

import anyio.to_thread
from mcp.server.fastmcp.exceptions import ToolError

from ema.core.errors import EmaError
from ema.core.logging import log_exception, write_event
from ema.core.workspace import Workspace


def _refusal(code: str, message: str) -> ToolError:
    return ToolError(json.dumps({"code": code, "message": message}, ensure_ascii=False))


async def call[T](ws: Workspace, tool: str, fn: Callable[[], T]) -> T:
    """Run a use case off the event loop; only the code and Romanian message leave Ema."""
    started = time.monotonic()

    def logged(outcome: str, code: str | None) -> None:
        with ws.app_log() as handle:
            write_event(
                handle,
                "mcp_tool",
                tool=tool,
                outcome=outcome,
                code=code,
                duration_ms=int((time.monotonic() - started) * 1000),
            )

    try:
        result = await anyio.to_thread.run_sync(fn)
    except EmaError as exc:
        with ws.app_log() as handle:
            write_event(handle, "interface_error", code=exc.code, detail=exc.detail)
        logged("error", exc.code)
        raise _refusal(exc.code, exc.user_message_ro) from None
    except Exception as exc:
        with ws.app_log() as handle:
            log_exception(handle, exc)
        logged("error", "internal_error")
        raise _refusal("internal_error", "Eroare internă Ema.") from None
    logged("ok", None)
    return result


def resolve_roots(ws: Workspace, import_roots: list[Path]) -> tuple[Path, ...]:
    for root in import_roots:
        if not root.is_dir():
            raise EmaError("import_root_invalid", "Directorul de import nu există.", str(root))
    return tuple(root.resolve(strict=True) for root in (ws.root / "imports", *import_roots))


def input_file(roots: tuple[Path, ...], value: str) -> Path:
    """An existing regular file whose real location, symlinks followed, is inside a root."""
    path = Path(value)
    if not path.is_absolute():
        raise EmaError(
            "path_outside_roots", "Fișierul este în afara directoarelor de import.", value
        )
    if not path.is_file():
        raise EmaError("file_missing", "Fișierul nu există.", value)
    resolved = path.resolve(strict=True)
    if not any(resolved.is_relative_to(root) for root in roots):
        raise EmaError(
            "path_outside_roots", "Fișierul este în afara directoarelor de import.", value
        )
    return resolved


def optional_file(roots: tuple[Path, ...], value: str | None) -> Path | None:
    return None if value is None else input_file(roots, value)
