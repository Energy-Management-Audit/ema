"""Blank totals require a simple SUM, and formula metadata is optional and lazy."""

import struct
from struct import pack, unpack_from

import olefile
import pytest
import xlwt
from tests.unit.energy_data.test_necesar_formula_totals import _book, _cache_zero
from xlrd.formula import FormulaError

from ema.core.office import sheet_formulas
from ema.core.office.sheet_formulas import formula_inputs_blank
from ema.core.office.sheets import open_book
from ema.energy_data.carriers import Carrier
from ema.energy_data.necesar import parse_necesar_info, to_dataset


@pytest.mark.parametrize("formula", ["=SUM(B3:M3)", "=sum( B3, M3 )", "=SUM($B$3)"])
def test_only_blank_sum_operands_prove_a_missing_total(formula):
    assert formula_inputs_blank(formula, "Totals", lambda *_args: None)
    assert not formula_inputs_blank(formula, "Totals", lambda *_args: 0)


@pytest.mark.parametrize(
    "formula",
    [
        "=5",
        "=SUM(B3:M3)+5",
        "=SUM(B3:M3,5)",
        "=COUNT(B3:M3)",
        "=IF(B3>0,1,0)",
        "=SUM(SUM(B3:M3))",
        "=SUM()",
        "=SUM(B3,)",
        "=SUM(B3:M3",
        '=SUM("unterminated)',
        "=SUM(B0)",
        "=SUM(B3 M3)",
        "=SUM([Other.xlsx]Sheet1!B3)",
        "=SHARED FMLA at rowx=2 colx=13",
    ],
)
def test_other_or_malformed_formulas_are_not_proven_blank(formula):
    assert not formula_inputs_blank(formula, "Totals", lambda *_args: None)


def test_cross_sheet_sum_requires_every_referenced_cell_to_be_blank():
    cells = {"Inputs here": {(3, 2): None}, "Totals": {(3, 3): None}}

    def read(sheet, row, col):
        return cells[sheet].get((row, col))

    formula = "=SUM('Inputs here'!B3,Totals!C3)"
    assert formula_inputs_blank(formula, "Totals", read)
    cells["Inputs here"][3, 2] = 0
    assert not formula_inputs_blank(formula, "Totals", read)
    assert not formula_inputs_blank("=SUM(Missing!B3)", "Totals", read)


def test_xls_decodes_only_the_explicitly_checked_total(tmp_path, monkeypatch):
    path = tmp_path / "formulas.xls"
    book = xlwt.Workbook()
    sheet = book.add_sheet("Totals")
    sheet.write(2, 13, xlwt.Formula("SUM(B3:M3)"))
    sheet.write(19, 0, xlwt.Formula("COUNT(B3:M3)"))
    book.save(str(path))
    _cache_zero(path)
    original = sheet_formulas.decompile_formula
    decoded = []

    def decode(*args, **kwargs):
        decoded.append((kwargs["browx"], kwargs["bcolx"]))
        if kwargs["browx"] == 19:
            raise AssertionError("unreadable unrelated formula")
        return original(*args, **kwargs)

    monkeypatch.setattr(sheet_formulas, "decompile_formula", decode)
    opened = open_book(path)
    try:
        assert opened.sheet("Totals").value(20, 1).value == 0
        assert decoded == []
        assert opened.sheet("Totals").formula_inputs_blank(3, 14)
        assert decoded == [(2, 13)]
        assert not opened.sheet("Totals").formula_inputs_blank(20, 1)
        assert opened.sheet("Totals").value(20, 1).value == 0
    finally:
        opened.close()


@pytest.mark.parametrize(
    "error", [AssertionError, ValueError, RuntimeError, FormulaError, struct.error]
)
def test_total_decode_failure_retains_the_cached_number(tmp_path, monkeypatch, error):
    path = tmp_path / "decode.xls"
    _book(path, True, ())

    def fail(*args, **kwargs):
        raise error("decode failed")

    monkeypatch.setattr(sheet_formulas, "decompile_formula", fail)
    info = parse_necesar_info(path)
    assert info.carriers[Carrier.lpg].years[2025].total.value == 0
    assert to_dataset(info).carriers[Carrier.lpg][2025].annual.value == 0


def test_xls_shared_formula_is_not_proven_blank(tmp_path):
    path = tmp_path / "shared.xls"
    _book(path, True, ())
    with olefile.OleFileIO(str(path), write_mode=True) as archive:
        data = bytearray(archive.openstream("Workbook").read())
        offset = 0
        while offset + 4 <= len(data):
            kind, length = unpack_from("<HH", data, offset)
            if kind == 6:
                # BIFF ptgExp references a shared formula; no direct SUM can be proven here.
                data[offset + 24 : offset + 26] = pack("<H", 5)
                data[offset + 26 : offset + 31] = b"\x01" + pack("<HH", 2, 13)
                break
            offset += 4 + length
        archive.write_stream("Workbook", bytes(data))
    info = parse_necesar_info(path)
    assert info.carriers[Carrier.lpg].years[2025].total.value == 0
    assert not info.carriers[Carrier.lpg].years[2025].total_inputs_blank
