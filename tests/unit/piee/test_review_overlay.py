"""Reviewed field values reach the PIEE data a draft is composed from (B3)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from tests.unit.piee.synthetic_piee import YEAR, piee_data

from ema.core.office.sheets import CellRef
from ema.core.review.models import Candidate, Cell, Field
from ema.energy_data.calc import tep_total
from ema.energy_data.carriers import Carrier
from ema.energy_data.model import Reading
from ema.piee.review_overlay import apply_review


def _field(key: str, value: Any, **changes: Any) -> Field:
    value_type = changes.pop("value_type", "number" if isinstance(value, Decimal) else "text")
    base: dict[str, Any] = {
        "id": key,
        "job_id": "job",
        "key": key,
        "label": key,
        "value_type": value_type,
        "value": value,
        "state": "extracted",
        "presence": "found" if value is not None else "not_found",
    }
    return Field.model_validate({**base, **changes})


def _corrected(key: str, value: Any, **changes: Any) -> Field:
    return _field(key, value, review="corrected", state="manual", evidence=["manual"], **changes)


def test_corrected_month_replaces_that_reading_only() -> None:
    data = piee_data()
    key = f"carrier.electricity_grid.{YEAR}.03"
    result = apply_review(data, [_corrected(key, Decimal("140.5"), unit="MWh")], {})
    series = result.dataset.carriers[Carrier.electricity_grid][YEAR]
    assert series.months[3] == Reading(140.5, "MWh")
    assert series.annual == Reading(1200.0, "MWh")
    assert result.prelucrare is not None
    assert f"tep.electricity_grid.{YEAR}.03" not in result.prelucrare.filed
    assert f"tep.total.{YEAR}.03" not in result.prelucrare.filed
    assert f"tep.electricity_grid.{YEAR}" in result.prelucrare.filed
    assert f"tep.total.{YEAR}" in result.prelucrare.filed
    assert data.dataset.carriers[Carrier.electricity_grid][YEAR].months[3].value == 100.0


def test_corrected_annual_drops_derived_figures_so_the_total_is_recomputed() -> None:
    data = piee_data()
    before = tep_total(data.dataset, data.factors, YEAR).value
    key = f"carrier.electricity_grid.{YEAR}"
    result = apply_review(data, [_corrected(key, Decimal("1500"), unit="MWh")], {})
    assert result.dataset.carriers[Carrier.electricity_grid][YEAR].annual == Reading(1500.0, "MWh")
    assert result.prelucrare is not None
    filed = result.prelucrare.filed
    for dropped in (
        f"tep.electricity_grid.{YEAR}",
        f"tep.total.{YEAR}",
        f"specific.total.{YEAR}",
    ):
        assert dropped not in filed
    assert YEAR not in result.dataset.filed_indicators["intensity"]
    after = tep_total(result.dataset, result.factors, YEAR).value
    assert before is not None and after is not None and after > before


def test_decided_total_survives_a_changed_carrier() -> None:
    fields = [
        _corrected(f"carrier.electricity_grid.{YEAR}", Decimal("1500"), unit="MWh"),
        _corrected("annual.total_tep", Decimal("150.25"), unit="tep"),
    ]
    result = apply_review(piee_data(), fields, {})
    assert result.prelucrare is not None
    assert result.prelucrare.filed[f"tep.total.{YEAR}"].value == 150.25


def test_chosen_total_is_filed_even_without_prelucrare() -> None:
    data = piee_data(prelucrare=False)
    field = _field(
        "annual.total_tep",
        Decimal("22161.92"),
        unit="tep",
        review="accepted",
        alternatives=[
            Candidate(id="c-calc", value=Decimal("22164.05"), evidence=["calc"]),
            Candidate(id="c-anexa", value=Decimal("22161.92"), evidence=["cell"]),
        ],
        chosen="c-anexa",
        confidence="exact",
        evidence=["cell"],
    )
    cells = {"cell": Cell(sheet="Date anuale", ref="Date anuale!F21")}
    result = apply_review(data, [field], cells)
    assert result.prelucrare is not None
    filed = result.prelucrare.filed[f"tep.total.{YEAR}"]
    assert filed.value == 22161.92
    assert filed.ref == CellRef("Date anuale", 21, 6)
    assert result.prelucrare.filed.keys() == {f"tep.total.{YEAR}"}
    assert result.dataset == data.dataset
    assert result.anexa == data.anexa


def test_rejected_value_is_absent_not_the_file_value() -> None:
    fields = [
        _field(f"carrier.natural_gas.{YEAR}", Decimal("500"), unit="MWh", review="rejected"),
        _field("identity.name", "Exemplu SA", review="rejected"),
        _field("measure.planned.1.investment_thousand_lei", Decimal("100"), review="rejected"),
    ]
    result = apply_review(piee_data(), fields, {})
    assert result.dataset.carriers[Carrier.natural_gas][YEAR].annual == Reading(None, "MWh")
    assert "name" not in result.anexa.identity
    measure = result.anexa.planned_measures[0]
    assert "investment_thousand_lei" not in measure.values
    assert "payback_years" not in measure.values


def test_filled_not_found_term_appears_with_a_review_reference() -> None:
    field = _corrected("measure.planned.2.commissioning_year", 2027, value_type="year")
    result = apply_review(piee_data(), [field], {})
    term = result.anexa.planned_measures[1].commissioning_year
    assert term is not None
    assert term.value == 2027
    assert term.ref == CellRef("review", 1, 1)
    assert term.label == "measure.planned.2.commissioning_year"


def test_pending_and_plainly_accepted_fields_change_nothing() -> None:
    data = piee_data()
    fields = [
        _field(f"carrier.electricity_grid.{YEAR}.03", Decimal("999"), unit="MWh"),
        _field("identity.name", "Altceva SA", review="accepted"),
    ]
    assert apply_review(data, fields, {}) == data


def test_payback_dropped_when_its_inputs_change_unless_decided() -> None:
    changed = _corrected("measure.planned.1.saving_thousand_lei", Decimal("50"))
    result = apply_review(piee_data(), [changed], {})
    assert "payback_years" not in result.anexa.planned_measures[0].values
    kept = [changed, _corrected("measure.planned.1.payback_years", Decimal("3"), unit="ani")]
    result = apply_review(piee_data(), kept, {})
    assert result.anexa.planned_measures[0].values["payback_years"].value == 3.0
