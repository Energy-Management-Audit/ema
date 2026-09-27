"""Bounded release check against the public Ema release repository."""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from http.client import HTTPException
from typing import Literal, cast

from ema.core.errors import EmaError
from ema.core.web import fetch_bytes

RELEASES_URL = "https://api.github.com/repos/Energy-Management-Audit/ema-releases/releases/latest"
RELEASE_PREFIX = "https://github.com/Energy-Management-Audit/ema-releases/releases/"
DOWNLOAD_PREFIX = RELEASE_PREFIX + "download/"
TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$", re.ASCII)
VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$", re.ASCII)


@dataclass(frozen=True)
class UpdateStatus:
    current: str
    latest: str | None
    newer: bool
    notes: str | None
    page_url: str | None
    download_url: str | None
    checked_at: str
    state: Literal["ok", "no_release", "unavailable"]


def check_update(  # noqa: C901, PLR0911
    current: str,
    *,
    fetch: Callable[..., tuple[str, str, bytes]] = fetch_bytes,
) -> UpdateStatus:
    checked_at = datetime.now(UTC).isoformat()

    def empty(state: Literal["no_release", "unavailable"]) -> UpdateStatus:
        return UpdateStatus(current, None, False, None, None, None, checked_at, state)

    try:
        _url, _content_type, body = fetch(RELEASES_URL, allowed_host="api.github.com")
    except (EmaError, HTTPException, OSError) as exc:
        if isinstance(exc, EmaError) and exc.code == "web_status" and exc.detail == "404":
            return empty("no_release")
        return empty("unavailable")
    try:
        payload: object = json.loads(body)
        if not isinstance(payload, dict):
            return empty("unavailable")
        release = cast(dict[str, object], payload)
        tag = release.get("tag_name")
        if not isinstance(tag, str) or (match := TAG.fullmatch(tag)) is None:
            return empty("unavailable")
        current_match = VERSION.fullmatch(current)
        if current_match is None:
            return empty("unavailable")
        latest = tag[1:]
        newer = tuple(map(int, match.groups())) > tuple(map(int, current_match.groups()))
        raw_notes = release.get("body")
        notes = raw_notes[:4000] or None if isinstance(raw_notes, str) else None
        raw_page = release.get("html_url")
        page_url = (
            raw_page if isinstance(raw_page, str) and raw_page.startswith(RELEASE_PREFIX) else None
        )
        raw_assets = release.get("assets")
        download_url = None
        if isinstance(raw_assets, list):
            for raw_asset in cast(list[object], raw_assets):
                if not isinstance(raw_asset, dict):
                    continue
                asset = cast(dict[str, object], raw_asset)
                if asset.get("name") != f"Ema-Setup-{latest}.exe":
                    continue
                url = asset.get("browser_download_url")
                if isinstance(url, str) and url.startswith(DOWNLOAD_PREFIX):
                    download_url = url
                    break
        if newer and page_url is None and download_url is None:
            page_url = RELEASE_PREFIX + "tag/" + tag
        return UpdateStatus(current, latest, newer, notes, page_url, download_url, checked_at, "ok")
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return empty("unavailable")
