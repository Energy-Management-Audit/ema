"""CLIENT-A1 legacy collection acceptance using the private reference library."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from docx import Document
from tests.workspace_jobs import create_job

from ema.core.config import Settings
from ema.core.intake import ItemOutcome, intake_legacy
from ema.core.jobs import StageContext, StageOutcome, run_stage, status, subscribe
from ema.core.office.convert import stored_file
from ema.core.office.sheets import open_book
from ema.core.office.sniff import FileKind, sniff
from ema.core.office.word_api import word_available
from ema.core.workspace import Workspace

pytestmark = [pytest.mark.golden, pytest.mark.word]


def _sources() -> list[Path]:
    reference = os.environ.get("EMA_REFERENCE")
    if not reference:
        pytest.skip("EMA_REFERENCE unavailable; golden not verified")
    received = Path(reference) / "audit/cases/audit-case-a/received"
    sources = sorted(path for path in received.iterdir() if path.suffix.lower() in {".doc", ".xls"})
    assert len(sources) == 12
    assert sum(path.suffix.lower() == ".doc" for path in sources) == 7
    return sources


def _collection(tmp_path: Path, sources: list[Path]) -> tuple[Workspace, str, dict[str, Path]]:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "CLIENT-A1-golden", 2026)
    by_slot = {}
    for number, source in enumerate(sources, 1):
        slot = f"dossier/{number:04}"
        ws.set_slot(job, slot, ws.add_file("CLIENT-A1-golden", source))
        by_slot[slot] = source
    return ws, job, by_slot


def _run(ws: Workspace, job: str) -> tuple[dict, list[ItemOutcome]]:
    results: list[ItemOutcome] = []

    def stage(ctx: StageContext) -> StageOutcome:
        return intake_legacy(ctx, "dossier", results.append)

    run = run_stage(ws, job, "intake", stage)
    for _ in subscribe(ws, job):
        pass
    recorded = next(entry for entry in status(ws, job).runs if entry["id"] == run)
    assert recorded["state"] == "ready", recorded["error"]
    assert recorded["publication"] == "current"
    assert len(results) == 12
    return recorded, results


def _print_table(results: list[ItemOutcome], by_slot: dict[str, Path]) -> None:
    print("name | kind | words orig/conv | outcome")
    for item in results:
        print(
            f"{by_slot[item.slot].name} | {item.kind.value} | "
            f"{item.original_words}/{item.converted_words} | {item.status}"
        )


def test_CLIENT-A1_legacy_collection_with_word(tmp_path: Path) -> None:
    sources = _sources()
    assert word_available(Settings()), "Word is required for the native golden"
    ws, job, by_slot = _collection(tmp_path, sources)
    recorded, results = _run(ws, job)
    _print_table(results, by_slot)

    assert not json.loads(recorded["outcome"])["item_failures"]
    assert {item.kind for item in results} == {FileKind.DOC, FileKind.XLS, FileKind.HTML}
    assert sum(item.status == "readable" for item in results) == 4
    assert sum(item.status == "html_as_xls" for item in results) == 1
    assert sum(item.status == "converted" for item in results) == 7
    html = next(item for item in results if by_slot[item.slot].name.startswith("13.4."))
    assert html.kind == FileKind.HTML and html.warning

    for item in results:
        source = by_slot[item.slot]
        assert sniff(source).kind == item.kind
        versions = ws.list_versions(job, item.slot)
        if item.kind == FileKind.XLS:
            assert len(versions) == 1
            book = open_book(source)
            assert book.sheet_names
            book.close()
        elif item.kind == FileKind.DOC:
            assert len(versions) == 2
            assert versions[1].converted_from == versions[0].file_sha
            assert versions[1].origin == "converted"
            _, converted = stored_file(ws, job, versions[1].file_sha)
            Document(converted)
            assert sniff(converted).kind == FileKind.DOCX
            assert item.original_words is not None and item.converted_words is not None
            assert item.original_words == item.converted_words or item.warning


def test_CLIENT-A1_legacy_collection_without_word(tmp_path: Path, monkeypatch) -> None:
    sources = _sources()
    monkeypatch.setenv("EMA_WORD_PATH", str(tmp_path / "missing-word.app"))
    ws, job, by_slot = _collection(tmp_path, sources)
    recorded, results = _run(ws, job)
    _print_table(results, by_slot)

    assert not json.loads(recorded["outcome"])["item_failures"]
    assert sum(item.status == "needs_conversion" for item in results) == 7
    assert sum(item.status == "readable" for item in results) == 4
    assert sum(item.status == "html_as_xls" for item in results) == 1
    for item in results:
        assert len(ws.list_versions(job, item.slot)) == 1
        if item.kind == FileKind.DOC:
            assert "save it as .docx" in (item.detail or "")
