"""Filed measure rows keep evidence and derive payback only from supplied costs."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from ema.core.office.sheets import CellRef
from ema.energy_data.anexa_cells import AnexaData, Measure
from ema.energy_data.source import Located
from ema.piee.measure_tables import _solution_row
from ema.piee.measures import measures, planned_period


def _value(value: str | float | int) -> Located:
    return Located(value, CellRef("Solutii EE", 6, 2))


def test_measures_keep_source_and_derive_payback() -> None:
    source = Measure(
        "planned",
        _value("measure"),
        _value(2027),
        {
            "investment_thousand_lei": _value(12.0),
            "saving_thousand_lei": _value(3.0),
        },
    )
    anexa = AnexaData(planned_measures=[source])
    rows = measures(anexa, planned=True)
    assert rows[0].payback_years == 4.0
    assert rows[0].payback_inputs == (
        source.values["investment_thousand_lei"],
        source.values["saving_thousand_lei"],
    )
    assert planned_period(rows) == (2027, 2027)


def test_no_savings_gives_missing_payback() -> None:
    source = Measure(
        "existing",
        _value("measure"),
        None,
        {
            "investment_thousand_lei": _value(12.0),
            "saving_thousand_lei": _value(0.0),
        },
    )
    rows = measures(AnexaData(existing_measures=[source]), planned=False)
    assert rows[0].payback_years is None
    assert rows[0].payback_inputs is None


def test_solution_row_follows_authored_payback_cost_and_saving_columns() -> None:
    source = Measure(
        "planned",
        _value("measure"),
        _value(2027),
        {
            "investment_thousand_lei": _value(12.0),
            "saving_thousand_lei": _value(3.0),
            "saving_mwh": _value(20.0),
            "saving_tep": _value(1.72),
        },
    )
    assert _solution_row(source) == (
        "measure",
        "2027",
        "4,00 (calculat)",
        "12,00",
        "20,00",
        "1,72",
    )
