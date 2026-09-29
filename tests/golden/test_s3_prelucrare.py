"""S3 reference comparisons against the auditor's delivered Prelucrare date workbooks."""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import NamedTuple

import pytest
from tests.golden.cases import case_path

from ema.energy_data.calc import annual, co2, indicators, specific_consumption, tep, tep_total
from ema.energy_data.carriers import Carrier, carrier_for
from ema.energy_data.factors import FACTORS_2026, FactorTable
from ema.energy_data.model import EnergyDataset

from .s3_book import MONTHS, Workbook, month_columns, norm, number, year
from .s3_expected import EXPECTED_DIFFERENCES
from .s3_filed import filed_relation, tep_total_excluding_pv
from .s3_workbooks import load_case, specific_cells

CASES = (
    (
        "piee-case-a",
        case_path("piee-case-a", "prelucrare"),
        (2022, 2023, 2024),
    ),
    (
        "piee-case-b",
        case_path("piee-case-b", "prelucrare"),
        (2023, 2024, 2025),
    ),
    (
        "audit-case-c",
        case_path("audit-case-c", "prelucrare"),
        (2022, 2023, 2024),
    ),
)

IGNORED_TEP_ROWS = {
    ("piee-case-b", "energie termica surse recupetrabile tep"): (
        "Filed recovered heat has no physical source in the S3 dataset or matching carrier."
    )
}

NOT_COMPARED = {
    ("piee-case-b", "TEP", "electricity_pv", 2024, None): (
        "Typed recovered-electricity annual value has no source sheet; filed totals exclude it."
    )
}


def _tep_cells(
    book: Workbook, years: tuple[int, ...], case: str
) -> list[tuple[int, Carrier | None, int | None, float]]:
    rows = book.sheet("TEP")
    result = []
    current_year = None
    columns: dict[int, int] = {}
    seen_rows: set[tuple[int, Carrier | None]] = set()
    for row in rows:
        if len(row) > 2 and year(row[2]) in years and not any(norm(v) in MONTHS for v in row):
            current_year = year(row[2])
            columns = {}
            continue
        seen = month_columns(row)
        if len(seen) == 12 and current_year is not None:
            columns = seen
            continue
        if current_year is None or not columns or len(row) < 3:
            continue
        label = norm(row[2])
        carrier = None if label == "total tep" else carrier_for(label)
        if (case, label) in IGNORED_TEP_ROWS:
            continue
        last_month = max(columns.values())
        filed_values = [number(row[column]) for column in columns.values() if column < len(row)]
        filed_values += [number(v) for v in row[last_month + 1 : last_month + 3]]
        if not label and not any(value is not None for value in filed_values):
            continue
        message = f"unmapped TEP row for {case}/{current_year}: {label!r}"
        assert carrier is not None or label == "total tep", message
        row_key = (current_year, carrier)
        assert row_key not in seen_rows, f"duplicate TEP carrier row: {case}/{row_key}"
        seen_rows.add(row_key)
        for month, column in columns.items():
            value = number(row[column]) if column < len(row) else None
            if value is not None:
                result.append((current_year, carrier, month, value))
        # The last numeric cell after December is the row's labelled TOTAL column.
        annual_values = [number(v) for v in row[last_month + 1 : last_month + 3]]
        annual_value = next((v for v in reversed(annual_values) if v is not None), None)
        if annual_value is not None:
            result.append((current_year, carrier, None, annual_value))
    return result


CellKey = tuple[str, str, str, int, int | None]


class ReviewContext(NamedTuple):
    seen: set[CellKey]
    unreviewed: list[str]
    book: Workbook
    ds: EnergyDataset
    factors: FactorTable


def _expected_or_match(
    key: CellKey,
    actual: float | None,
    missing: tuple[str, ...],
    filed: float,
    context: ReviewContext,
) -> tuple[int, int]:
    if actual is not None and math.isclose(actual, filed, rel_tol=1e-9, abs_tol=1e-9):
        assert key not in EXPECTED_DIFFERENCES, f"stale expected difference: {key}"
        return 1, 0
    if key in EXPECTED_DIFFERENCES:
        expected = EXPECTED_DIFFERENCES[key]
        if expected.kind == "missing":
            assert actual is None, f"expected missing value for {key}: {actual}"
            reason_matches = any(item.startswith(expected.check) for item in missing)
            message = (
                f"missing reason changed for {key}: expected {expected.check!r}, got {missing}"
            )
            assert reason_matches, message
            if expected.filed_state == "filed_zero":
                assert filed == 0, f"expected filed zero for {key}"
            elif expected.filed_state == "filed_blank":
                assert filed is None, f"expected filed blank for {key}"
            elif expected.filed_state == "filed_relation":
                assert expected.filed_check is not None, f"missing filed relation for {key}"
                expected_filed = filed_relation(
                    expected.filed_check, key, context.book, context.ds, context.factors
                )
                assert filed is not None and math.isclose(
                    filed, expected_filed, rel_tol=1e-9, abs_tol=1e-9
                ), f"expected filed relation failed for {key}"
            else:
                raise AssertionError(f"unreviewed filed state for {key}")
        else:
            expected_actual, expected_filed = _relation_values(
                expected.check, key, context.book, context.ds, context.factors
            )
            assert (
                actual is not None
                and expected_actual is not None
                and math.isclose(actual, expected_actual, rel_tol=1e-9, abs_tol=1e-9)
            ), f"expected Ema relation failed for {key}: {actual} vs {expected_actual}"
            assert expected_filed is not None and math.isclose(
                filed, expected_filed, rel_tol=1e-9, abs_tol=1e-9
            ), f"expected filed relation failed for {key}: filed={filed}, expected={expected_filed}"
        context.seen.add(key)
        print(f"EXPECTED {key}: filed={filed}, recomputed={actual}")
        return 0, 1
    context.unreviewed.append(f"{key}: computed={actual}, filed={filed}")
    return 0, 0


def _relation_values(
    name: str, key: CellKey, book: Workbook, ds: EnergyDataset, factors: FactorTable
) -> tuple[float | None, float | None]:
    item_year = key[3]
    if name == "diesel_specific":
        petrol = tep(ds, factors, Carrier.petrol, item_year).value
        production = annual(ds.production["main"][item_year], "production", "main", item_year)
        expected_actual = (
            petrol / production.value if petrol is not None and production.value else None
        )
        filed = specific_consumption(ds, factors, item_year, Carrier.diesel, "main").value
        return expected_actual, filed
    if name == "scaled_intensity":
        energy = tep_total(ds, factors, item_year).value
        turnover = ds.turnover_lei[item_year].value
        expected_actual = energy / (turnover / 1000) if energy is not None and turnover else None
        return expected_actual, expected_actual * 1000 if expected_actual is not None else None
    if name == "impact_diesel_input":
        current_year = None
        matches = []
        for row in book.sheet("impact de mediu"):
            possible = year(row[1]) if len(row) > 1 else None
            if possible is not None:
                current_year = possible
            if current_year == item_year and len(row) > 7 and norm(row[1]) == "motorina":
                quantity, factor = number(row[4]), number(row[7])
                if quantity is not None and factor is not None:
                    matches.append(quantity * factor)
        assert len(matches) == 1, f"ambiguous diesel impact source for {item_year}"
        physical = annual(
            ds.carriers[Carrier.diesel][item_year], "carrier", Carrier.diesel.value, item_year
        ).value
        factor = factors.co2_factor(Carrier.diesel, "t", item_year)
        expected_actual = physical * factor.per_unit if physical is not None and factor else None
        return expected_actual, matches[0]
    if name == "production_value_intensity":
        rows = book.sheet("Chelt-Cifra afaceri")
        header = next(row for row in rows if any(norm(v) == "anul" for v in row))
        columns = [i for i, value in enumerate(header) if year(value) == item_year]
        matches = [
            number(row[columns[0]])
            for row in rows
            if len(columns) == 1
            and len(row) > max(2, columns[0])
            and "valoarea totala a productiei anuale realizate si vandute" in norm(row[2])
        ]
        assert len(matches) == 1 and matches[0], f"ambiguous production value for {item_year}"
        energy = tep_total(ds, factors, item_year).value
        turnover = ds.turnover_lei[item_year].value
        expected_actual = energy / (turnover / 1000) if energy is not None and turnover else None
        expected_filed = energy / (matches[0] / 1000) if energy is not None else None
        return expected_actual, expected_filed
    raise AssertionError(f"unknown expected relation: {name}")


def _assert_coverage(
    case: str,
    years: tuple[int, ...],
    tep_cells: list[tuple[int, Carrier | None, int | None, float]],
    co2_filed: dict[tuple[int, Carrier | None], float],
    specific_filed: dict[tuple[int, Carrier | None], float],
) -> None:
    assert tep_cells, f"no TEP cells read for {case}"
    for item_year in years:
        total_periods = {
            month for y, carrier, month, _ in tep_cells if y == item_year and carrier is None
        }
        assert total_periods == {
            *range(1, 13),
            None,
        }, f"TEP total coverage incomplete for {case}/{item_year}"
        assert (item_year, None) in co2_filed, f"CO2 total missing for {case}/{item_year}"
    required_specific = {(y, None) for y in years}
    message = f"specific total coverage incomplete for {case}"
    assert required_specific <= specific_filed.keys(), message


def _accounted_co2_subtotal(ds, factors, item_year, co2_filed) -> float | None:
    parts = []
    for year_key, carrier in co2_filed:
        if year_key != item_year or carrier is None:
            continue
        annual_part = co2(ds, factors, item_year, carrier).value
        if annual_part is not None:
            parts.append(annual_part)
            continue
        monthly = [co2(ds, factors, item_year, carrier, month).value for month in range(1, 13)]
        if not any(value is not None for value in monthly):
            return None
        parts.append(sum(value for value in monthly if value is not None))
    return sum(parts)


@pytest.mark.golden
@pytest.mark.parametrize(("case", "relative", "years"), CASES)
def test_prelucrare(case: str, relative: str, years: tuple[int, ...]) -> None:  # noqa: C901, PLR0912, PLR0915
    root = os.environ.get("EMA_REFERENCE")
    if not root:
        pytest.skip("EMA_REFERENCE is required")
    book, ds, factors, co2_filed, intensity_filed = load_case(Path(root) / relative, case, years)
    calculated = indicators(ds, factors)
    matched = differences = not_compared = 0
    seen: set[tuple[str, str, str, int, int | None]] = set()
    unreviewed: list[str] = []
    context = ReviewContext(seen, unreviewed, book, ds, factors)
    tep_cells = _tep_cells(book, years, case)
    specific_filed = specific_cells(book, years)
    _assert_coverage(case, years, tep_cells, co2_filed, specific_filed)
    for item_year, carrier, month, filed in tep_cells:
        result = (
            tep_total(ds, factors, item_year, month)
            if carrier is None
            else tep(ds, factors, carrier, item_year, month)
        )
        label = carrier.value if carrier is not None else "total"
        key = (case, "TEP", label, item_year, month)
        if key in NOT_COMPARED:
            assert result.value is None and f"carrier.{label}.{item_year}" in result.missing
            not_compared += 1
            continue
        a, b = _expected_or_match(
            key,
            result.value,
            result.missing,
            filed,
            context,
        )
        matched += a
        differences += b
        if case == "piee-case-b" and carrier is None and result.value is None:
            months = (month,) if month is not None else range(1, 13)
            available = (
                tep(ds, factors, item, item_year, current_month).value
                for item in ds.carriers
                if item_year in ds.carriers[item]
                for current_month in months
            )
            subtotal = sum(value for value in available if value is not None)
            assert math.isclose(subtotal, filed, rel_tol=1e-9, abs_tol=1e-9)
    for (item_year, carrier), filed in co2_filed.items():
        result = co2(ds, factors, item_year, carrier)
        label = carrier.value if carrier is not None else "total"
        a, b = _expected_or_match(
            (case, "impact de mediu", label, item_year, None),
            result.value,
            result.missing,
            filed,
            context,
        )
        matched += a
        differences += b
        if carrier is None and result.value is None:
            accounted = _accounted_co2_subtotal(ds, factors, item_year, co2_filed)
            if accounted is not None and not (case == "piee-case-a" and item_year == 2022):
                assert math.isclose(accounted, filed, rel_tol=1e-9, abs_tol=1e-9)
    for item_year, filed in intensity_filed.items():
        a, b = _expected_or_match(
            (case, "Chelt-Cifra afaceri", "intensity", item_year, None),
            calculated.intensity[item_year].value,
            calculated.intensity[item_year].missing,
            filed,
            context,
        )
        matched += a
        differences += b
    for (item_year, carrier), filed in specific_filed.items():
        result = specific_consumption(ds, factors, item_year, carrier, "main")
        label = carrier.value if carrier is not None else "total"
        value = result.value
        if case == "piee-case-a" and carrier == Carrier.electricity_grid:
            pv = specific_consumption(ds, factors, item_year, Carrier.electricity_pv, "main")
            value = value + pv.value if value is not None and pv.value is not None else None
        a, b = _expected_or_match(
            (case, "Consumuri specifice", label, item_year, None),
            value,
            result.missing,
            filed,
            context,
        )
        matched += a
        differences += b
    unused = {key for key in EXPECTED_DIFFERENCES if key[0] == case and key not in seen}
    assert not unused, f"unexercised expected differences: {unused}"
    if case == "piee-case-b":
        assert not_compared == 1
        assert all(tep_total_excluding_pv(book, item_year, None) for item_year in (2024, 2025))
    assert not unreviewed, "\n".join(unreviewed[:80]) + f"\n{len(unreviewed)} unreviewed"
    differing_default = 0
    for factor in (*factors.tep, *factors.co2):
        default = (
            FACTORS_2026.tep_factor(factor.carrier, factor.unit, 2026)
            if factor in factors.tep
            else FACTORS_2026.co2_factor(factor.carrier, factor.unit, 2026)
        )
        if default is None or default.per_unit != factor.per_unit:
            differing_default += 1
    print(
        f"{case}: compared={matched + differences}, matched={matched}, "
        f"expected_differences={differences}, not_compared={not_compared}, "
        f"default_factor_gaps={differing_default}, "
        "evidence=2(reference)"
    )
