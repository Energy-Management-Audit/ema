"""Chart and numbered-table comparisons for the case C document golden."""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest
from docx import Document
from openpyxl import load_workbook
from tests.golden.cases import case_path

from ema.consumption_analysis.analysis import Metric, value
from ema.core.office.chart_series import read_series
from ema.core.office.package import REL_CHART, C, R, read_parts, relationships, target_part, xml
from ema.energy_data.calc import tep
from ema.energy_data.carriers import Carrier
from ema.energy_data.source import normal
from ema.piee.chart_plan import MONTHS
from ema.piee.dataset import PieeData

S16 = frozenset({10, 18, 22, 24, 33, 34})


def _order(path: Path) -> list[str]:
    parts = read_parts(path)
    linked = {
        relation.get("Id"): target_part("word/document.xml", relation.get("Target", ""))
        for relation in relationships(parts, "word/document.xml")
        if relation.get("Type") == REL_CHART
    }
    return [
        linked[node.get(f"{{{R}}}id")]
        for node in xml(parts, "word/document.xml").iter(f"{{{C}}}chart")
    ]


def _source(data: PieeData, ordinal: int, index: int) -> float:
    assert data.prelucrare is not None
    if ordinal in {10, 18, 22}:
        carrier = {
            10: Carrier.natural_gas,
            18: Carrier.diesel,
            22: Carrier.coke,
        }[ordinal]
        reading = data.prelucrare.dataset.carriers[carrier][2024].months[index + 1]
        return reading.value
    if ordinal == 24:
        reading = data.prelucrare.dataset.carriers[Carrier.coke][2023 + index].annual
        assert reading is not None
        return reading.value
    key = "coke" if ordinal == 33 else "total"
    found = data.prelucrare.filed[f"specific.{key}.{2023 + index}"]
    assert isinstance(found.value, int | float)
    return float(found.value)


def _compare_figures(actual: Path, final: Path, data: PieeData) -> None:
    produced, delivered = _order(actual), _order(final)
    assert len(produced) == len(delivered) == 39
    assert len(set(produced)) == 39
    chart_parts = read_parts(actual)
    assert (
        sum(bool(list(xml(chart_parts, part).iter(f"{{{C}}}barChart"))) for part in produced) == 36
    )
    assert (
        sum(bool(list(xml(chart_parts, part).iter(f"{{{C}}}pie3DChart"))) for part in produced) == 3
    )
    for ordinal, (actual_part, delivered_part) in enumerate(
        zip(produced, delivered, strict=True), 1
    ):
        actual_series = read_series(actual, actual_part)
        delivered_series = read_series(final, delivered_part)
        if ordinal in {17, 18, 19, 20}:
            # S16: the 2024 GPL cache is stale; S17: the other GPL series are zero.
            assert len(actual_series) == 1 and len(delivered_series) == 2
            if ordinal == 18:
                assert any(value not in {None, 0} for value in delivered_series[1].values)
                _zero_gpl_source()
            else:
                assert all(value in {None, 0} for value in delivered_series[1].values)
            delivered_series = delivered_series[:1]
        assert len(actual_series) == len(delivered_series), ordinal
        for actual_item, delivered_item in zip(actual_series, delivered_series, strict=True):
            actual_values, delivered_values = actual_item.values, delivered_item.values
            if ordinal == 30:
                # S17: the authored 2025 pie retains a zero-only GPL category.
                assert len(actual_values) == 4 and len(delivered_values) == 5
                assert sum(value == 0 for value in delivered_values) == 1
                delivered_values = [value for value in delivered_values if value != 0]
            assert len(actual_values) == len(delivered_values), ordinal
            for index, (actual_value, delivered_value) in enumerate(
                zip(actual_values, delivered_values, strict=True)
            ):
                if actual_value is None or delivered_value is None:
                    assert actual_value is delivered_value, (ordinal, index)
                elif math.isclose(actual_value, delivered_value, rel_tol=1e-8, abs_tol=1e-8):
                    continue
                else:
                    assert ordinal in S16, (ordinal, index)
                    assert math.isclose(
                        actual_value, _source(data, ordinal, index), rel_tol=1e-9, abs_tol=1e-9
                    )


def _zero_gpl_source() -> None:
    book = load_workbook(case_path("piee-case-c", "prelucrare"), read_only=True, data_only=True)
    for sheet_name in ("Consum Carburanti", "TEP"):
        sheet = book[sheet_name]
        rows = [
            row
            for row in sheet.iter_rows()
            if any(
                normal(cell.value) == "gpl" or normal(cell.value).startswith("gpl ")
                for cell in row
                if isinstance(cell.value, str)
            )
        ]
        assert (
            len(
                [
                    row
                    for row in rows
                    if sum(isinstance(cell.value, int | float) for cell in row) >= 12
                ]
            )
            >= 3
        )
        assert all(
            cell.value == 0 for row in rows for cell in row if isinstance(cell.value, int | float)
        )


def _number(text: str) -> float:
    assert re.fullmatch(r"[\d. ,]+", text.strip()), text
    return float(text.strip().replace(" ", "").replace(".", "").replace(",", "."))


def _gas_total_is_sourced(data: PieeData) -> None:
    book = load_workbook(case_path("piee-case-c", "prelucrare"), read_only=True, data_only=True)
    sheet = next(book[name] for name in book.sheetnames if normal(name) == "consum gaz")
    for row in sheet.iter_rows():
        if 2024 not in [cell.value for cell in row]:
            continue
        total_col = next(
            (index for index, cell in enumerate(row) if normal(str(cell.value or "")) == "total"),
            None,
        )
        if total_col is None:
            continue
        year_cell = next(cell for cell in row if cell.value == 2024)
        monthly = next(sheet.iter_rows(min_row=year_cell.row + 1, max_row=year_cell.row + 1))
        months_by_name = {normal(name) for name in MONTHS}
        month_cols = [
            index
            for index, cell in enumerate(row)
            if normal(str(cell.value or "")) in months_by_name
        ]
        assert len(month_cols) == 12 and max(month_cols) < total_col
        months = [monthly[index].value for index in month_cols]
        assert len(months) == 12 and all(isinstance(item, int | float) for item in months)
        total = monthly[total_col].value
        assert isinstance(total, int | float)
        assert math.isclose(sum(months), total, rel_tol=1e-9, abs_tol=1e-9)
        sourced = value(
            data.dataset, data.factors, Metric("carrier", (Carrier.natural_gas,)), 2024
        )[0]
        assert sourced is not None and math.isclose(sourced, total, rel_tol=1e-9, abs_tol=1e-9)
        return
    pytest.fail("labelled 2024 gas TOTAL not found")


def _compare_annual_tables(final: Path, data: PieeData) -> None:
    tables = [
        table
        for table in Document(final).tables
        if len(table.rows) >= 3
        and len(table.columns) >= 5
        and normal(table.cell(0, 0).text) == "anul"
        and normal(table.cell(0, 1).text) == "u m"
    ]
    carriers = (
        Carrier.electricity_grid,
        Carrier.natural_gas,
        Carrier.electricity_cogen,
        Carrier.diesel,
        Carrier.coke,
    )
    assert len(tables) == len(carriers)
    slips = {
        (Carrier.natural_gas, 2024, 1): "S18",
        (Carrier.diesel, 2024, 1): "S6",
        (Carrier.diesel, 2024, 2): "S6",
        (Carrier.coke, 2024, 1): "S7",
    }
    for table, carrier in zip(tables, carriers, strict=True):
        for column, year in enumerate(data.dataset.years, 2):
            raw = value(data.dataset, data.factors, Metric("carrier", (carrier,)), year)[0]
            equivalent = tep(data.dataset, data.factors, carrier, year).value
            assert raw is not None and equivalent is not None
            for row, sourced in ((1, raw), (2, equivalent)):
                authored = _number(table.cell(row, column).text)
                same = round(authored, 2) == round(sourced, 2)
                slip = slips.get((carrier, year, row))
                assert same == (slip is None), (carrier, year, row, slip)
    _gas_total_is_sourced(data)


def _compare_centralizer(actual: Path, final: Path, data: PieeData) -> None:
    authored = next(
        table
        for table in Document(final).tables
        if len(table.rows) == 7
        and {normal(row.cells[0].text) for row in table.rows} >= {"cocs", "gaze naturale", "total"}
    )
    produced = next(
        table
        for table in Document(actual).tables
        if len(table.rows) == 4
        and {normal(cell.text) for cell in table.rows[0].cells} >= {"cocs", "gaz natural", "total"}
    )
    produced_cols = {normal(cell.text): index for index, cell in enumerate(produced.rows[0].cells)}
    authored_rows = {normal(row.cells[0].text): row for row in authored.rows}
    carriers = (
        ("energie electrica din sen", "energie electrica", Carrier.electricity_grid),
        ("gaz natural", "gaze naturale", Carrier.natural_gas),
        ("carburant", "motorina", Carrier.diesel),
        ("cocs", "cocs", Carrier.coke),
    )
    for year_index, year in enumerate(data.dataset.years, 1):
        assert int(produced.cell(year_index, 0).text) == year
        for produced_label, authored_label, carrier in carriers:
            source = tep(data.dataset, data.factors, carrier, year).value
            assert source is not None
            column = next(
                index for label, index in produced_cols.items() if label.startswith(produced_label)
            )
            output = _number(produced.cell(year_index, column).text)
            assert round(output, 2) == round(source, 2)
            reference = _number(authored_rows[authored_label].cells[year_index].text)
            slip = carrier == Carrier.electricity_grid and year == 2024  # S2
            assert (round(reference, 2) == round(source, 2)) != slip
        total = value(data.dataset, data.factors, Metric("tep_total"), year)[0]
        assert total is not None
        output = _number(produced.cell(year_index, produced_cols["total"]).text)
        reference = _number(authored_rows["total"].cells[year_index].text)
        assert round(output, 2) == round(total, 2)
        assert (round(reference, 2) == round(total, 2)) != (year == 2024)  # S3
