"""Collection slot ordering and stage staleness contracts."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from tests.workspace_jobs import create_job

from ema.core.errors import EmaError
from ema.core.jobs import StageContext, StageOutcome, get_job, latest_ready_run, run_stage, status
from ema.core.workspace import Workspace
from ema.invoices import export


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    return Workspace(tmp_path / "workspace")


def file(ws: Workspace, tmp_path: Path, content: str) -> str:
    source = tmp_path / f"{content}.txt"
    source.write_text(content, encoding="utf-8")
    return ws.add_file("client", source)


def wait_run(ws: Workspace, job: str) -> dict[str, object]:
    for _ in range(200):
        result = status(ws, job)
        if result.state != "running":
            return result.runs[-1]
        time.sleep(0.01)
    pytest.fail("stage did not finish")


def test_collection_slots_order_and_removed_version(ws: Workspace, tmp_path: Path) -> None:
    job = create_job(ws, "invoices", "client", None)
    first = file(ws, tmp_path, "first")
    second = file(ws, tmp_path, "second")
    ws.set_slot(job, "invoices/0002", first)
    ws.set_slot(job, "invoices/0001", first)
    ws.set_slot(job, "invoices/0001", second)
    ws.remove_version(job, "invoices/0001", 2)
    assert ws.list_slots(job, "invoices") == ["invoices/0001", "invoices/0002"]

    def stage(ctx):  # type: ignore[no-untyped-def]
        versions = ctx.read_slots("invoices")
        assert [version.file_sha for version in versions] == [first, first]
        return StageOutcome()

    run_stage(ws, job, "extract", stage)
    assert wait_run(ws, job)["publication"] == "current"
    assert latest_ready_run(ws, job, "extract") == status(ws, job).runs[-1]["id"]


def test_read_slots_can_skip_individual_slot_reads(ws: Workspace, tmp_path: Path) -> None:
    job = create_job(ws, "invoices", "client", None)
    sha = file(ws, tmp_path, "first")
    ws.set_slot(job, "invoices/0001", sha)
    ctx = StageContext(ws, job, "run", "intake")

    versions = ctx.read_slots("invoices", record=False)

    assert [version.slot for version in versions] == ["invoices/0001"]
    assert ("slots.collection", f"{job}:invoices") in ctx.reads
    assert ("slots", f"{job}:invoices/0001") not in ctx.reads


def test_get_job_returns_client_identity(ws: Workspace) -> None:
    job = create_job(ws, "invoices", "client", None)
    assert get_job(ws, job)["client_slug"] == "client"


@pytest.mark.parametrize("change", ["replace", "append", "remove"])
def test_collection_change_stales_stage(ws: Workspace, tmp_path: Path, change: str) -> None:
    job = create_job(ws, "invoices", "client", None)
    first = file(ws, tmp_path, "first")
    second = file(ws, tmp_path, "second")
    ws.set_slot(job, "invoices/0001", first)
    read = threading.Event()
    release = threading.Event()

    def stage(ctx):  # type: ignore[no-untyped-def]
        assert len(ctx.read_slots("invoices")) == 1
        read.set()
        assert release.wait(2)
        return StageOutcome()

    run_stage(ws, job, "extract", stage)
    assert read.wait(2)
    if change == "replace":
        ws.set_slot(job, "invoices/0001", second)
    elif change == "append":
        ws.set_slot(job, "invoices/0002", second)
    else:
        ws.remove_version(job, "invoices/0001", 1)
    release.set()
    run = wait_run(ws, job)
    assert run["publication"] == "stale", run["error"]


def test_invoice_export_rejects_changed_slot(ws: Workspace, tmp_path: Path) -> None:
    job = create_job(ws, "invoices", "client", None)
    first = file(ws, tmp_path, "first")
    second = file(ws, tmp_path, "second")
    ws.set_slot(job, "invoices/0001", first)

    def stage(ctx):  # type: ignore[no-untyped-def]
        ctx.read_slots("invoices")
        (ctx.artifact_dir() / "outcomes.json").write_text("[]", encoding="utf-8")
        return StageOutcome()

    run_stage(ws, job, "invoices", stage)
    assert wait_run(ws, job)["publication"] == "current"
    ws.set_slot(job, "invoices/0001", second)
    with ws.connect() as db:
        destination = ws.job_path(db, job) / "outputs" / "Facturi.xlsx"
    with pytest.raises(EmaError) as error:
        export(ws, job, destination)
    assert error.value.code == "invoices_stale"
