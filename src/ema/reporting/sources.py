"""Select the newest indexed annex per year and beneficiary."""

from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Any

from ema.clients.registry import get_client
from ema.core.workspace import Workspace
from ema.energy_data.annex_index import indexed


def select_sources(
    ws: Workspace, client_ids: list[str]
) -> tuple[list[tuple[str, str, Path, Path]], list[dict[str, Any]]]:
    sources: list[tuple[str, str, Path, Path]] = []
    absent: list[dict[str, Any]] = []
    annexes = indexed(ws)
    for client_id in client_ids:
        get_client(ws, client_id)
        records = annexes.get(client_id, [])
        if not records:
            absent.append(
                {"client_id": client_id, "code": "annex_missing", "detail": "Anexa lipseşte."}
            )
            continue
        seen: set[tuple[int, str]] = set()
        for record in records:
            beneficiary = " ".join(str(record.data.get("name") or "").casefold().split())
            key = (record.year, beneficiary)
            if key in seen:
                continue
            seen.add(key)
            raw_name = str(record.data.get("file_name") or f"{record.sha}.xlsx")
            display_name = unicodedata.normalize("NFC", raw_name)
            sources.append(
                (
                    client_id,
                    record.sha,
                    ws.file_path(client_id, record.sha),
                    Path(client_id, display_name),
                )
            )
    return sources, absent
