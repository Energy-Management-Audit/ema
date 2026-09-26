"""The PIEE import stage, and generation that reuses it instead of re-reading (B1, B2, B7)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.unit.piee.synthetic_piee import YEAR, piee_data

from ema.api import create_app
from ema.core.jobs import create_job, status, subscribe
from ema.core.review import conflicts, decide, fields, log, propose
from ema.core.review.models import Cell, Evidence, FieldSpec
from ema.core.workspace import Workspace
from ema.energy_data.carriers import Carrier
from ema.piee import workflow
from ema.piee.dataset import PieeData
from ema.piee.review_workflow import PieeWorkflow

BASE = "http://127.0.0.1:8766"
SOURCES = ("anexa", "questionnaire")


@dataclass
class Composed:
    untouched: list[str] = field(default_factory=list[str])
    package_issues: list[str] = field(default_factory=list[str])
    leftover_parts: list[str] = field(default_factory=list[str])
    final_ready: bool = True


@dataclass
class Fakes:
    imports: int = 0
    composed: list[PieeData] = field(default_factory=list[PieeData])


def _evidence(key: str) -> list[Evidence]:
    return [
        Evidence(
            id=f"{key}-{datetime.now(UTC).timestamp()}",
            provenance="document",
            file_sha="synthetic",
            locator=Cell(sheet="Anexa", ref="Anexa!C7"),
            method="anexa",
            retrieved_at=datetime.now(UTC),
            highlight="exact",
        )
    ]


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Fakes:
    state = Fakes()

    def fake_import(ws: Workspace, job: str, *_args: Any, **_kwargs: Any) -> None:
        state.imports += 1
        month = FieldSpec(
            key=f"carrier.electricity_grid.{YEAR}.03", label="m", value_type="number", unit="MWh"
        )
        propose(ws, job, month, Decimal("100"), _evidence("m"), state="extracted")
        total = FieldSpec(key="annual.total_tep", label="t", value_type="number", unit="tep")
        for value in ("146", "147"):
            propose(ws, job, total, Decimal(value), _evidence(value), state="extracted")

    def fake_compose(data: PieeData, _base: Path, output: Path, _today: object) -> Composed:
        state.composed.append(data)
        output.write_bytes(b"synthetic draft")
        return Composed()

    base = tmp_path / "base"
    base.mkdir()
    monkeypatch.setattr(workflow, "load", lambda *_args, **_kwargs: piee_data())
    monkeypatch.setattr(workflow, "import_piee_into_job", fake_import)
    monkeypatch.setattr(workflow, "base_directory", lambda _ws: base)
    monkeypatch.setattr(workflow, "load_approved_base", lambda _base: Composed())
    monkeypatch.setattr(Composed, "base_sha", "synthetic-base", raising=False)
    monkeypatch.setattr(workflow, "compose_draft", fake_compose)
    monkeypatch.setattr(
        workflow, "write_prelucrare", lambda *args: Path(args[2]).write_bytes(b"PK")
    )
    return state


def _job(ws: Workspace, tmp_path: Path, slots: tuple[str, ...] = SOURCES) -> str:
    job = create_job(ws, "piee", "synthetic", YEAR + 1)
    for slot in slots:
        source = tmp_path / f"{slot}.xlsx"
        source.write_bytes(slot.encode())
        ws.set_slot(job, slot, ws.add_file("synthetic", source))
    return job


def _wait(ws: Workspace, job: str, run: str) -> dict[str, Any]:
    for _ in subscribe(ws, job):
        pass
    return next(item for item in status(ws, job).runs if item["id"] == run)


def _client(ws: Workspace) -> tuple[TestClient, dict[str, str]]:
    client = TestClient(create_app(ws, 8766, launch_code="code"), base_url=BASE)
    csrf = client.post("/session", json={"code": "code"}).json()["csrf"]
    return client, {"x-ema-csrf": csrf}


def test_import_endpoint_starts_a_run_that_reads_every_source_slot(
    fakes: Fakes, tmp_path: Path
) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = _job(ws, tmp_path)
    client, headers = _client(ws)
    revision = client.get(f"/jobs/{job}").json()["revision"]
    started = client.post(
        f"/jobs/{job}/piee/import", json={"on_revision": revision}, headers=headers
    )
    assert started.status_code == 202
    body = started.json()
    assert body["stage"] == "piee_import" and body["state"] == "running"
    assert _wait(ws, job, body["run_id"])["state"] == "ready"
    assert fakes.imports == 1
    with ws.connect() as db:
        reads = {
            str(row["row_id"])
            for row in db.execute(
                "SELECT row_id FROM run_reads WHERE run_id=? AND table_name='slots'",
                (body["run_id"],),
            )
        }
    assert reads == {f"{job}:{slot}" for slot in SOURCES}
    events = client.get(f"/jobs/{job}/events").text
    assert "Citire documente PIEE" in events and "Date citite" in events


def test_import_refusals(fakes: Fakes, tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    client, headers = _client(ws)
    no_anexa = _job(ws, tmp_path, ("questionnaire",))
    stale = _job(ws, tmp_path)
    invoices = create_job(ws, "invoices", "synthetic", None)
    cases = (
        (no_anexa, None, 409, "not_ready"),
        (stale, 0, 409, "stale_revision"),
        (invoices, None, 400, "wrong_job_type"),
    )
    for job, revision, code, problem in cases:
        current = client.get(f"/jobs/{job}").json()["revision"]
        response = client.post(
            f"/jobs/{job}/piee/import",
            json={"on_revision": current if revision is None else revision},
            headers=headers,
        )
        assert response.status_code == code, problem
        assert response.json()["type"] == f"urn:ema:error:{problem}"
    assert fakes.imports == 0


def test_generate_requires_a_current_import(fakes: Fakes, tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = _job(ws, tmp_path)
    client, headers = _client(ws)
    revision = client.get(f"/jobs/{job}").json()["revision"]
    refused = client.post(
        f"/jobs/{job}/piee/generate",
        json={"kind": "draft", "on_revision": revision},
        headers=headers,
    )
    assert refused.status_code == 409
    assert refused.json() == {
        "type": "urn:ema:error:import_required",
        "title": "Documentele trebuie citite din nou.",
        "status": 409,
    }
    codes = {issue.code for issue in PieeWorkflow().readiness(ws, job).blocking}
    assert "import_required" in codes
    assert fakes.imports == 0


def test_decisions_reach_the_draft_without_a_second_import(fakes: Fakes, tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = _job(ws, tmp_path)
    _wait(ws, job, workflow.start_import_for_job(ws, job))
    by_key = {item.key: item for item in fields(ws, job)}
    month = by_key[f"carrier.electricity_grid.{YEAR}.03"]
    conflict = conflicts(ws, job)[0]
    decide(ws, job, month.id, "correct", month.revision, "user", value="140.5")
    chosen = next(item for item in conflict.alternatives if item.value == Decimal("147"))
    decide(ws, job, conflict.id, "choose", conflict.revision, "user", alternative=chosen.id)
    before = {item.id: (item.value, item.revision) for item in fields(ws, job)}
    decisions = [item.id for item in log(ws, job)]
    assert "import_required" not in {i.code for i in PieeWorkflow().readiness(ws, job).blocking}

    run = workflow.start_generate_for_job(ws, job)
    record = _wait(ws, job, run)
    assert record["state"] == "ready", record["error"]
    assert fakes.imports == 1
    assert {item.id: (item.value, item.revision) for item in fields(ws, job)} == before
    assert [item.id for item in log(ws, job)] == decisions
    composed = fakes.composed[-1]
    assert composed.dataset.carriers[Carrier.electricity_grid][YEAR].months[3].value == 140.5
    assert composed.prelucrare is not None
    assert composed.prelucrare.filed[f"tep.total.{YEAR}"].value == 147.0


def test_a_changed_slot_requires_a_new_import(fakes: Fakes, tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = _job(ws, tmp_path)
    _wait(ws, job, workflow.start_import_for_job(ws, job))
    replacement = tmp_path / "anexa-2.xlsx"
    replacement.write_bytes(b"another anexa")
    ws.set_slot(job, "anexa", ws.add_file("synthetic", replacement))
    codes = {issue.code for issue in PieeWorkflow().readiness(ws, job).blocking}
    assert "import_required" in codes
    with pytest.raises(Exception) as refused:
        workflow.start_generate_for_job(ws, job)
    assert getattr(refused.value, "code", None) == "import_required"
    added = _job(ws, tmp_path, ("anexa",))
    _wait(ws, added, workflow.start_import_for_job(ws, added))
    extra = tmp_path / "necesar.xlsx"
    extra.write_bytes(b"necesar")
    ws.set_slot(added, "questionnaire", ws.add_file("synthetic", extra))
    assert workflow.current_import(ws, added) is None


def test_cli_start_generate_imports_then_drafts(fakes: Fakes, tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    anexa = tmp_path / "anexa.xlsx"
    anexa.write_bytes(b"anexa")
    job, run = workflow.start_generate(ws, workflow.GenerateRequest("synthetic", YEAR, anexa))
    record = _wait(ws, job, run)
    assert record["state"] == "ready", record["error"]
    assert fakes.imports == 1
    stages = [item["stage"] for item in status(ws, job).runs]
    assert stages == ["piee_import", "piee_generate"]


def test_checks_answer_before_a_draft(fakes: Fakes, tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = _job(ws, tmp_path)
    client, _headers = _client(ws)
    checks = client.get(f"/jobs/{job}/export/checks")
    assert checks.status_code == 200
    codes = {issue["code"] for issue in checks.json()["readiness"]["blocking"]}
    assert "draft_missing" in codes
    assert PieeWorkflow().readiness_snapshot(ws, job) == {"run": None}
