"""The measures-screen summary (B4), the measures view (B8) and fillable measure gaps (B9)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.unit.piee.synthetic_piee import YEAR, piee_data

from ema.api import create_app
from ema.core.jobs import create_job
from ema.core.review import decide, fields, mark_absent, propose
from ema.core.review.models import Cell, Evidence, FieldSpec
from ema.core.workspace import Workspace
from ema.piee import intake
from ema.piee.views import list_measures, summary

BASE = "http://127.0.0.1:8766"


def _evidence(key: str) -> list[Evidence]:
    return [
        Evidence(
            id=f"{key}-{datetime.now(UTC).timestamp()}",
            provenance="document",
            file_sha="synthetic",
            locator=Cell(sheet="Solutii EE planificate", ref="Solutii EE planificate!C7"),
            method="anexa",
            retrieved_at=datetime.now(UTC),
            highlight="exact",
        )
    ]


def _put(ws: Workspace, job: str, key: str, value: Any, unit: str | None = None) -> None:
    value_type = "number" if isinstance(value, Decimal) else "text"
    spec = FieldSpec(key=key, label=key, value_type=value_type, unit=unit)
    propose(ws, job, spec, value, _evidence(key), state="extracted")


def _measure(ws: Workspace, job: str, group: str, index: int, **values: Any) -> None:
    for column, value in values.items():
        key = f"measure.{group}.{index}.{column}"
        if value is None:
            kind = "year" if column == "commissioning_year" else "number"
            mark_absent(ws, job, FieldSpec(key=key, label=key, value_type=kind), "not_found")
        else:
            _put(ws, job, key, value)


def _seed(ws: Workspace) -> str:
    job = create_job(ws, "piee", "synthetic", YEAR + 1)
    full = {
        "investment_thousand_lei": Decimal("100"),
        "saving_mwh": Decimal("10.5"),
        "payback_years": Decimal("4"),
        "commissioning_year": Decimal("2026"),
    }
    _measure(ws, job, "planned", 1, description="Izolare", **full)
    _measure(
        ws,
        job,
        "planned",
        2,
        description="Iluminat",
        investment_thousand_lei=Decimal("50"),
        saving_mwh=Decimal("2"),
        payback_years=Decimal("3"),
        commissioning_year=None,
    )
    _measure(ws, job, "planned", 3, description="Pompe", saving_mwh=None)
    _measure(ws, job, "existing", 1, description="Existenta", **full)
    return job


def test_summary_sums_planned_measures_only(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    job = _seed(ws)
    result = summary(ws, job)
    assert result["savings_mwh"]["value"] == Decimal("12.5")
    assert result["savings_mwh"]["unit"] == "MWh/an"
    assert result["savings_mwh"]["missing"] == ["measure.planned.3"]
    assert len(result["savings_mwh"]["field_ids"]) == 2
    assert result["investment_thousand_lei"]["value"] == Decimal("150")
    assert result["investment_thousand_lei"]["unit"] == "mii lei"
    assert result["measures_total"] == 4
    assert result["measures_complete"] == 2
    assert result["measures_without_term"] == 2
    assert result["total_tep"]["value"] is None
    assert result["annual_check"] == "missing"


def test_rejected_measure_values_leave_the_sums(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    job = _seed(ws)
    field = next(f for f in fields(ws, job) if f.key == "measure.planned.2.saving_mwh")
    decide(ws, job, field.id, "reject", field.revision, "user")
    result = summary(ws, job)
    assert result["savings_mwh"]["value"] == Decimal("10.5")
    assert result["savings_mwh"]["missing"] == ["measure.planned.2", "measure.planned.3"]


def test_annual_check_states(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    job = create_job(ws, "piee", "synthetic", YEAR + 1)
    assert summary(ws, job)["annual_check"] == "missing"
    _put(ws, job, "annual.total_tep", Decimal("146"), "tep")
    assert summary(ws, job)["annual_check"] == "match"
    assert summary(ws, job)["total_tep"]["value"] == Decimal("146")
    _put(ws, job, "annual.total_tep", Decimal("147"), "tep")
    assert summary(ws, job)["annual_check"] == "mismatch"
    field = next(f for f in fields(ws, job) if f.key == "annual.total_tep")
    decide(
        ws, job, field.id, "choose", field.revision, "user", alternative=field.alternatives[0].id
    )
    assert summary(ws, job)["annual_check"] == "decided"


def test_summary_route_and_wrong_job_type(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    job = _seed(ws)
    invoices = create_job(ws, "invoices", "synthetic", None)
    client = TestClient(create_app(ws, 8766, launch_code="code"), base_url=BASE)
    client.post("/session", json={"code": "code"})
    response = client.get(f"/jobs/{job}/piee/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["measures_total"] == 4
    assert body["savings_mwh"]["value"] == "12.5"
    wrong = client.get(f"/jobs/{invoices}/piee/summary")
    assert wrong.status_code == 400
    assert wrong.json()["type"] == "urn:ema:error:wrong_job_type"


def test_measures_view_reads_saving_mwh(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    job = _seed(ws)
    measure = next(item for item in list_measures(ws, job) if item["id"] == "measure.planned.1")
    assert measure["savings_mwh"] == 10.5


def test_absent_measure_columns_become_fillable_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path / "workspace")
    monkeypatch.setattr(intake, "load", lambda *_args, **_kwargs: piee_data())
    anexa = tmp_path / "anexa.xlsx"
    anexa.write_bytes(b"anexa")
    job = create_job(ws, "piee", "synthetic", YEAR + 1)
    intake.import_piee_into_job(ws, job, YEAR, anexa, None)
    by_key = {item.key: item for item in fields(ws, job)}
    second = "measure.planned.2"
    for column, unit in (
        ("investment_thousand_lei", "mii lei"),
        ("commissioning_year", None),
        ("payback_years", "ani"),
    ):
        field = by_key[f"{second}.{column}"]
        assert field.presence == "not_found" and field.value is None
        assert field.unit == unit
    assert by_key[f"{second}.commissioning_year"].value_type == "year"
    assert "measure.planned.1.saving_mwh" in by_key
    assert by_key["measure.planned.1.saving_mwh"].presence == "not_found"
    term = by_key[f"{second}.commissioning_year"]
    decided = decide(ws, job, term.id, "correct", term.revision, "user", value="2027")
    assert decided.after.value == 2027  # type: ignore[union-attr]
