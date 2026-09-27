"""Session-protected update status with an app-local refresh interval."""

import time
from datetime import UTC, datetime
from threading import Lock
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from ema import __version__
from ema.core.updates import UpdateStatus, check_update


class UpdateInfo(BaseModel):
    current: str
    latest: str | None
    newer: bool
    notes: str | None
    page_url: str | None
    download_url: str | None
    checked_at: str
    state: Literal["ok", "no_release", "unavailable"]


def install_update_routes(app: FastAPI, *, mock: bool) -> None:
    last: UpdateStatus | None = None
    last_at = 0.0
    cache_lock = Lock()

    @app.get("/settings/update", tags=["settings"], response_model=UpdateInfo)
    def get_update() -> UpdateStatus:
        nonlocal last, last_at
        with cache_lock:
            now = time.monotonic()
            lifetime = 600 if last is not None and last.state == "unavailable" else 21600
            if last is not None and now - last_at < lifetime:
                return last
        if mock:
            result = UpdateStatus(
                __version__,
                None,
                False,
                None,
                None,
                None,
                datetime.now(UTC).isoformat(),
                "no_release",
            )
        else:
            result = check_update(__version__)
        with cache_lock:
            now = time.monotonic()
            lifetime = 600 if last is not None and last.state == "unavailable" else 21600
            if last is not None and now - last_at < lifetime:
                return last
            last = result
            last_at = now
            return result
