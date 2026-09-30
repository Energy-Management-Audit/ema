"""piee-case-c: every filed component is present and S11 remains a review conflict."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from tests.golden.cases import case_path
from tests.workspace_jobs import register_client

from ema.core.review import fields
from ema.core.workspace import Workspace
from ema.energy_data.carriers import Carrier
from ema.energy_data.model import EnergyDataset
from ema.piee.annual_check import annual_check
from ema.piee.dataset import load
from ema.piee.intake import import_piee
from ema.piee.review_workflow import PieeWorkflow

pytestmark = pytest.mark.golden


def test_piee_case_c_components_totals_and_s11(tmp_path: Path) -> None:
    anexa = case_path("piee-case-c", "anexa")
    prelucrare = case_path("piee-case-c", "prelucrare")
    data = load(2025, anexa, None, prelucrare)
    assert data.annual_check.status == "match"
    assert data.annual_check.missing_carriers == ()
    assert tuple(check.year for check in data.annual_check.years) == (2023, 2024, 2025)
    for yearly in data.annual_check.years:
        assert yearly.missing_carriers == ()
        assert yearly.unfiled_carriers == ()
        assert all(check.status == "match" for check in (*yearly.components, *yearly.totals))
        assert f"tep.internal_total.{yearly.year}" in {check.key for check in yearly.totals}
        for check in (*yearly.components, *yearly.totals):
            assert check.filed.ref.a1
            assert check.computed.value is not None
    latest = data.annual_check.years[-1]
    assert {check.key for check in latest.components if check.source == "anexa"} >= {
        f"anexa.tep.{carrier.value}.2025"
        for carrier in (Carrier.diesel, Carrier.coke, Carrier.natural_gas, Carrier.electricity_grid)
    }
    assert "annual.total_tep" in {check.key for check in latest.totals}

    [s11] = [item for item in data.disagreements if item.key == "co2.coke.2025"]
    assert s11.chosen_source == "calculated"
    assert s11.alternative_source == "prelucrare_filed"
    assert s11.chosen_location is not None and s11.alternative_location is not None
    assert s11.chosen_location.ref.a1 != s11.alternative_location.ref.a1

    ws = Workspace(tmp_path / "workspace")
    register_client(ws, "piee-case-c")
    job = import_piee(ws, "piee-case-c", 2025, anexa, None, prelucrare)
    readiness = PieeWorkflow().readiness(ws, job.id)
    assert not any(issue.code == "carrier_incomplete" for issue in readiness.blocking)
    assert not readiness.final_ok
    assert any(field.key == "co2.coke.2025" for field in fields(ws, job.id, status="conflict"))


def test_missing_coke_blocks_each_year(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = load(
        2025, case_path("piee-case-c", "anexa"), None, case_path("piee-case-c", "prelucrare")
    )
    source = data.dataset
    without_coke = EnergyDataset(
        source.years,
        {carrier: years for carrier, years in source.carriers.items() if carrier != Carrier.coke},
        source.production,
        source.production_unit,
        source.turnover_lei,
        source.energy_costs_lei,
        source.filed_indicators,
        source.energy_inventory_complete,
        source.production_name,
    )
    assert data.prelucrare is not None
    checked = annual_check(
        data.anexa,
        data.year,
        without_coke,
        data.factors,
        data.prelucrare.located,
        data.prelucrare.filed,
    )
    assert checked.status == "incomplete"
    assert checked.missing_carriers == ("coke",)
    assert all(Carrier.coke in year.missing_carriers for year in checked.years)

    monkeypatch.setattr(
        "ema.piee.intake.load",
        lambda *_args, **_kwargs: replace(data, dataset=without_coke, annual_check=checked),
    )
    ws = Workspace(tmp_path / "workspace")
    register_client(ws, "piee-case-c")
    job = import_piee(
        ws,
        "piee-case-c",
        2025,
        case_path("piee-case-c", "anexa"),
        None,
        case_path("piee-case-c", "prelucrare"),
    )
    readiness = PieeWorkflow().readiness(ws, job.id)
    assert not readiness.final_ok
    assert len([issue for issue in readiness.blocking if issue.code == "carrier_incomplete"]) == 3
