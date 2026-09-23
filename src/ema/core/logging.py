"""Structured local logs; workspace owns their paths and handles."""

import json
import logging
import subprocess
import traceback
from datetime import UTC, datetime
from typing import IO


def write_event(handle: IO[str], event: str, **fields: object) -> None:
    handle.write(
        json.dumps(
            {"at": datetime.now(UTC).isoformat(), "event": event, **fields}, ensure_ascii=False
        )
        + "\n"
    )
    handle.flush()


def log_exception(handle: IO[str], exc: BaseException) -> None:
    write_event(
        handle, "exception", error=str(exc), traceback="".join(traceback.format_exception(exc))
    )


def capture_child(proc: subprocess.Popen[str], handle: IO[str]) -> None:
    if proc.stderr is None:
        return
    for line in proc.stderr:
        write_event(handle, "child_stderr", line=line.rstrip("\n"))


def configure_app_log(handle: IO[str]) -> None:
    logger = logging.getLogger("ema")
    logger.addHandler(logging.StreamHandler(handle))
    logger.setLevel(logging.INFO)
