"""Best-effort diagnostics without interrupting a run state transition."""

import sys
import traceback

from ema.core.logging import log_exception
from ema.core.workspace import Workspace


def record_failure(ws: Workspace, job: str, exc: BaseException) -> None:
    try:
        with ws.connect() as db, ws.job_log(db, job) as handle:
            log_exception(handle, exc)
    except BaseException as log_error:
        try:
            with ws.app_log() as handle:
                log_exception(handle, exc)
                log_exception(handle, log_error)
        except BaseException as app_log_error:
            try:
                traceback.print_exception(exc, file=sys.stderr)
                traceback.print_exception(log_error, file=sys.stderr)
                traceback.print_exception(app_log_error, file=sys.stderr)
            except BaseException:
                return  # Diagnostics cannot interrupt the run state transition.
