"""Months against the filed annual reading: a difference beyond rounding blocks the final (C1)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from ema.api import create_app
from ema.core.jobs import create_job
from ema.core.review import decide, fields, propose
from ema.core.review.models import Cell, Evidence, Field, FieldSpec
from ema.core.workspace import Workspace
from ema.piee.annual_check import months_check
from ema.piee.review_workflow import PieeWorkflow

CODE = "months_annual_mismatch"
MESSAGE = "Suma lunilor nu se potriveşte cu totalul anual."
BASE = "http://127.0.0.1:8766"
ANNUAL = "carrier.natural_gas.2024"


def _readings(annual: str, months: list[str]) -> dict[str, tuple[Decimal, str | None]]:
    readings: dict[str, tuple[Decimal, str | None]] = {ANNUAL: (Decimal(annual), "MWh")}
    for month, value in enumerate(months, 1):
        readings[f"{ANNUAL}.{month:02d}"] = (Decimal(value), "MWh")
    return readings


def test_months_that_sum_to_the_annual_within_rounding_pass() -> None:
    assert months_check(_readings("120", ["10"] * 12)) == []
    assert months_check(_readings("120.4", ["10.0"] * 12)) == []


def test_a_sum_beyond_rounding_is_a_mismatch() -> None:
    [found] = months_check(_readings("120", ["10"] * 11 + ["25"]))
    assert found.annual_key == ANNUAL
    assert found.months_sum == Decimal(135) and found.annual == Decimal(120)


def test_incomplete_months_other_units_and_no_annual_are_not_checked() -> None:
    readings = _readings("120", ["10"] * 11 + ["25"])
    assert months_check({k: v for k, v in readings.items() if not k.endswith(".12")}) == []
    assert months_check({k: v for k, v in readings.items() if k != ANNUAL}) == []
    assert months_check({**readings, ANNUAL: (Decimal(120), "kWh")}) == []


def _evidence(key: str) -> list[Evidence]:
    return [
        Evidence(
            id=f"{key}-evidence",
            provenance="document",
            file_sha="synthetic",
            locator=Cell(sheet="Necesar", ref="Necesar!C7"),
            method="questionnaire",
            retrieved_at=datetime.now(UTC),
            highlight="exact",
        )
    ]


def _job(ws: Workspace) -> str:
    job = create_job(ws, "piee", "synthetic", 2025)
    for key, value in [(ANNUAL, "120"), *((f"{ANNUAL}.{m:02d}", "10") for m in range(1, 13))]:
        spec = FieldSpec(key=key, label=key, value_type="number", unit="MWh")
        propose(ws, job, spec, Decimal(value), _evidence(key), state="extracted")
    return job


def _field(ws: Workspace, job: str, key: str) -> Field:
    return next(field for field in fields(ws, job) if field.key == key)


def _codes(ws: Workspace, job: str) -> list[str]:
    return [issue.code for issue in PieeWorkflow().readiness(ws, job).blocking]


def test_readiness_blocks_after_a_month_correction_until_the_annual_is_corrected(
    tmp_path: Path,
) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = _job(ws)
    assert CODE not in _codes(ws, job)

    month = _field(ws, job, f"{ANNUAL}.03")
    decide(ws, job, month.id, "correct", month.revision, "user", value="25")
    blocking = PieeWorkflow().readiness(ws, job).blocking
    [issue] = [issue for issue in blocking if issue.code == CODE]
    assert issue.field_id == _field(ws, job, ANNUAL).id and issue.message == MESSAGE
    assert not PieeWorkflow().readiness(ws, job).final_ok

    annual = _field(ws, job, ANNUAL)
    decide(ws, job, annual.id, "correct", annual.revision, "user", value="135")
    assert CODE not in _codes(ws, job)


def test_a_rejected_month_leaves_nothing_to_compare(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = _job(ws)
    month = _field(ws, job, f"{ANNUAL}.03")
    decide(ws, job, month.id, "correct", month.revision, "user", value="25")
    month = _field(ws, job, f"{ANNUAL}.03")
    decide(ws, job, month.id, "reject", month.revision, "user")
    assert CODE not in _codes(ws, job)


def test_http_journey_month_correction_blocks_and_annual_correction_clears(
    tmp_path: Path,
) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = _job(ws)
    client = TestClient(create_app(ws, 8766, launch_code="code"), base_url=BASE)
    headers = {"x-ema-csrf": client.post("/session", json={"code": "code"}).json()["csrf"]}

    def correct(key: str, value: str) -> None:
        field = _field(ws, job, key)
        answer = client.post(
            f"/jobs/{job}/fields/{field.id}/decide",
            json={"action": "correct", "value": value, "on_revision": field.revision},
            headers=headers,
        )
        assert answer.status_code == 200, answer.text

    def blocking() -> list[dict[str, object]]:
        checks = client.get(f"/jobs/{job}/export/checks")
        assert checks.status_code == 200
        return [i for i in checks.json()["readiness"]["blocking"] if i["code"] == CODE]

    assert blocking() == []
    correct(f"{ANNUAL}.03", "25")
    assert blocking() == [
        {"code": CODE, "field_id": _field(ws, job, ANNUAL).id, "message": MESSAGE}
    ]
    correct(ANNUAL, "135")
    assert blocking() == []


def test_the_contract_note_names_the_code_and_message() -> None:
    note = Path("openapi/s17b-diff.md").read_text(encoding="utf-8")
    assert f"`{CODE}`" in note and MESSAGE in note
