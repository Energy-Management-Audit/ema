"""Component completeness and sourced reconciliation before a PIEE total can match."""

from __future__ import annotations

from pathlib import Path

from tests.workspace_jobs import create_job

from ema.core.office.sheets import CellRef
from ema.core.review import decide, fields, mark_absent
from ema.core.review.models import FieldSpec
from ema.core.workspace import Workspace
from ema.energy_data.anexa_cells import AnexaData
from ema.energy_data.calc import co2
from ema.energy_data.carriers import CARRIER_NAMES_RO, Carrier
from ema.energy_data.factors import Factor, FactorTable
from ema.energy_data.model import CarrierSeries, Derived, EnergyDataset, Reading
from ema.energy_data.necesar_model import Consumption, NecesarInfo, YearValues
from ema.energy_data.prelucrare_types import PrelucrareData
from ema.energy_data.source import Located
from ema.piee.dataset import _same_filed, assemble
from ema.piee.review_workflow import PieeWorkflow

YEAR = 2025


def _cell(sheet: str, value: float, decimals: int | None = 3, unit: str | None = None) -> Located:
    return Located(value, CellRef(sheet, 1, 1), unit=unit, displayed_decimals=decimals)


def _inputs() -> tuple[AnexaData, NecesarInfo]:
    anexa = AnexaData(year=_cell("Date anuale", YEAR, 0))
    anexa.annual["total_tep"] = _cell("Date anuale", 0.086)
    anexa.annual["electricity_grid_tep"] = _cell("Date anuale", 0.086)
    necesar = NecesarInfo()
    necesar.carriers[Carrier.electricity_grid] = Consumption(
        _cell("Necesar", 1),
        {YEAR: YearValues((None,) * 12, _cell("Necesar", 1, unit="MWh"))},
    )
    return anexa, necesar


def test_component_completeness_conflict_and_extra_carrier() -> None:
    anexa, necesar = _inputs()
    complete = assemble(YEAR, anexa, necesar)
    assert complete.annual_check.status == "match"
    assert complete.annual_check.missing_carriers == ()
    assert complete.annual_check.years[-1].components[0].key == "anexa.tep.electricity_grid.2025"

    anexa.annual["electricity_grid_tep"] = _cell("Date anuale", 0.0860000000001)
    assert assemble(YEAR, anexa, necesar).annual_check.status == "match"
    anexa.annual["electricity_grid_tep"] = _cell("Date anuale", 0.086)

    anexa.annual["diesel_tep"] = _cell("Date anuale", 1)
    incomplete = assemble(YEAR, anexa, necesar)
    assert incomplete.annual_check.status == "incomplete"
    assert incomplete.annual_check.missing_carriers == ("diesel",)

    anexa.annual.pop("diesel_tep")
    anexa.annual["electricity_grid_tep"] = _cell("Date anuale", 0.1)
    conflict = assemble(YEAR, anexa, necesar)
    assert conflict.annual_check.status == "conflict"
    [disagreement] = [
        item for item in conflict.disagreements if item.key == "anexa.tep.electricity_grid.2025"
    ]
    assert disagreement.chosen_location is not None
    assert disagreement.alternative_location is anexa.annual["electricity_grid_tep"]

    anexa.annual["electricity_grid_tep"] = _cell("Date anuale", 0.086)
    necesar.carriers[Carrier.natural_gas] = Consumption(
        _cell("Necesar", 1), {YEAR: YearValues((None,) * 12, _cell("Necesar", 1, unit="MWh"))}
    )
    extra = assemble(YEAR, anexa, necesar)
    assert extra.annual_check.unfiled_carriers == ("natural_gas",)


def test_unknown_precision_uses_tolerance_and_real_difference_keeps_cells() -> None:
    computed = Derived(0.1 + 0.2, "tep", "tep.carrier", ("carrier.diesel.2025",))
    assert _same_filed(_cell("TEP", 0.3, None), computed, {})
    assert not _same_filed(_cell("TEP", 0.31, None), computed, {})


def test_internal_generation_is_excluded_from_components_and_total() -> None:
    anexa, necesar = _inputs()
    imported = PrelucrareData(
        EnergyDataset(
            (YEAR,),
            {Carrier.electricity_cogen: {YEAR: CarrierSeries(annual=Reading(5, "MWh"))}},
        ),
        FactorTable(
            "synthetic",
            YEAR,
            (
                Factor(Carrier.electricity_cogen, "MWh", 0.086, "sheet!A1"),
                Factor(Carrier.electricity_grid, "MWh", 0.086, "sheet!A2"),
            ),
            (),
        ),
        filed={"tep.total.2025": _cell("TEP", 0.086)},
    )
    result = assemble(YEAR, anexa, necesar, imported)
    assert result.annual_check.status == "match"
    assert result.annual_check.unfiled_carriers == ()
    assert not any(
        item.key.startswith("tep.carrier.electricity_cogen") for item in result.disagreements
    )


def test_co2_converts_through_two_factors_from_same_sheet() -> None:
    dataset = EnergyDataset(
        (YEAR,), {Carrier.coke: {YEAR: CarrierSeries(annual=Reading(10, "MWh"))}}
    )
    factors = FactorTable(
        "synthetic",
        YEAR,
        (
            Factor(Carrier.coke, "MWh", 0.1, "book:Consum Cocs!F5"),
            Factor(Carrier.coke, "t", 0.5, "book:Consum Cocs!F4"),
        ),
        (Factor(Carrier.coke, "t", 2, "book:impact!H1", YEAR),),
    )
    calculated = co2(dataset, factors, YEAR, Carrier.coke)
    assert calculated.value == 4
    assert calculated.inputs == (
        "carrier.coke.2025",
        "factor.tep.coke.MWh",
        "factor.tep.coke.t",
        "factor.co2.coke.2025",
    )
    anexa, necesar = _inputs()
    filed = _cell("impact", 5, 0)
    source = _cell("Consum Cocs", 10, 0, "MWh")
    imported = PrelucrareData(
        dataset,
        factors,
        {"carrier.coke.2025": source},
        filed={"co2.coke.2025": filed},
    )
    [conflict] = [
        item
        for item in assemble(YEAR, anexa, necesar, imported).disagreements
        if item.key == "co2.coke.2025"
    ]
    assert conflict.chosen.value == 4
    assert conflict.alternative.value == 5
    assert conflict.chosen_location is source
    assert conflict.alternative_location is filed
    unavailable = FactorTable("synthetic", YEAR, factors.tep[:1], factors.co2)
    assert co2(dataset, unavailable, YEAR, Carrier.coke).value is None


def test_manual_review_clears_carrier_incomplete(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "piee", "synthetic", YEAR)
    spec = FieldSpec(
        key="carrier.coke.2025",
        label=CARRIER_NAMES_RO[Carrier.coke],
        value_type="number",
        unit="tep",
        required=True,
    )
    missing = mark_absent(ws, job, spec, "not_found")
    [issue] = [
        issue
        for issue in PieeWorkflow().readiness(ws, job).blocking
        if issue.code == "carrier_incomplete"
    ]
    assert issue.field_id == missing.id
    assert issue.message == "Lipseşte consumul de cocs pentru 2025."
    decide(ws, job, missing.id, "correct", missing.revision, "user", value="1")
    assert not any(
        issue.code == "carrier_incomplete" for issue in PieeWorkflow().readiness(ws, job).blocking
    )
    assert next(field for field in fields(ws, job) if field.id == missing.id).state == "manual"
