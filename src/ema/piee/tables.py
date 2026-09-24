"""Monthly and environmental values in the bookmarked PIEE table prototypes."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from pathlib import Path

from lxml import etree

from ema.consumption_analysis.analysis import Metric, value
from ema.core.office.anchor_targets import find_cell
from ema.core.office.anchors import AnchorLedger
from ema.core.office.cell_text import set_cell_text
from ema.core.office.package import encoded, read_parts, write_parts, xml
from ema.energy_data.carriers import Carrier
from ema.piee.chart_plan import BINDINGS, chart_series
from ema.piee.dataset import PieeData
from ema.piee.number import prototype_number

MONTHLY_TABLES: tuple[tuple[int, int, int], ...] = (
    (49, 1, 0),
    (51, 1, 6),
    (104, 5, 0),
    (106, 5, 6),
    (138, 9, 0),
    (140, 9, 6),
    (184, 13, 0),
    (186, 13, 6),
    (221, 17, 0),
    (223, 17, 6),
)


def _monthly(data: PieeData, chart_number: int) -> list[float | None]:
    binding = next(item for item in BINDINGS if item.slot == f"chart_{chart_number}")
    series = chart_series(data, binding)
    present = [item for item in series if item is not None]
    if not present:
        return [None] * 12
    result: list[float | None] = []
    for month in range(12):
        values = [item.values[month] for item in present]
        result.append(
            None if any(item is None for item in values) else sum(item or 0 for item in values)
        )
    return result


def _cell(
    root: etree._Element,
    slot: str,
    value: float | int | None,
    ledger: AnchorLedger,
    decimals: int = 2,
    grouping: bool = False,
) -> None:
    cell = find_cell([root], slot)
    formatted = (
        prototype_number(value, decimals, grouping=grouping) if value is not None else "n.d."
    )
    set_cell_text(
        cell,
        formatted,
        missing=value is None,
    )
    ledger.record(slot)


def _tep(data: PieeData, carrier: Carrier, year: int) -> float | None:
    key = f"tep.{carrier.value}.{year}"
    filed = data.prelucrare.filed.get(key) if data.prelucrare is not None else None
    if filed is not None and isinstance(filed.value, int | float):
        return float(filed.value)
    return value(data.dataset, data.factors, Metric("tep", (carrier,)), year)[0]


def _sum_present(values: tuple[float | None, ...]) -> float | None:
    return (
        sum(item for item in values if item is not None)
        if any(item is not None for item in values)
        else None
    )


def _equivalent(data: PieeData, year: int) -> tuple[float | None, ...]:
    electricity = _sum_present(
        (_tep(data, Carrier.electricity_grid, year), _tep(data, Carrier.electricity_pv, year))
    )
    gas = _tep(data, Carrier.natural_gas, year)
    fuel = _sum_present(
        tuple(
            _tep(data, carrier, year) for carrier in (Carrier.diesel, Carrier.petrol, Carrier.lpg)
        )
    )
    filed = data.prelucrare.filed.get(f"tep.total.{year}") if data.prelucrare is not None else None
    total = (
        float(filed.value)
        if filed is not None and isinstance(filed.value, int | float)
        else value(data.dataset, data.factors, Metric("tep_total"), year)[0]
    )
    return electricity, gas, fuel, total


def render_tables(source: Path, data: PieeData, output: Path, ledger: AnchorLedger) -> None:
    """Fill table cells through their bookmarks; years follow the selected analysis period."""
    parts = read_parts(source)
    root = xml(parts, "word/document.xml")
    for table_number, first_chart, month_offset in MONTHLY_TABLES:
        for row in range(1, 4):
            year = data.year - 3 + row
            values = _monthly(data, first_chart + row - 1)
            _cell(root, f"table_{table_number}_r{row}_c0", year, ledger, 0)
            for col in range(1, 7):
                _cell(
                    root,
                    f"table_{table_number}_r{row}_c{col}",
                    values[month_offset + col - 1],
                    ledger,
                    grouping=True,
                )
        ledger.record(f"table_{table_number}_rows")
    for row in range(1, 4):
        year = data.year - 3 + row
        binding = next(item for item in BINDINGS if item.slot == "chart_31")
        series = chart_series(data, binding)[0]
        emission = series.values[row - 1] if series is not None else None
        _cell(root, f"table_382_r{row}_c0", year, ledger, 0)
        _cell(root, f"table_382_r{row}_c1", emission, ledger, 0, True)
    ledger.record("table_382_rows")
    for row in range(1, 4):
        year = data.year - 3 + row
        _cell(root, f"table_277_r{row}_c0", year, ledger, 0)
        for col, item in enumerate(_equivalent(data, year), 1):
            _cell(root, f"table_277_r{row}_c{col}", item, ledger, grouping=True)
    ledger.record("table_277_rows")
    parts["word/document.xml"] = encoded(root)
    write_parts(parts, output)
