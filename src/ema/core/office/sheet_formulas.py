"""Conservative blank-SUM detection; optional formula decoding never blocks cached data."""

from collections.abc import Callable, Iterator
from pathlib import Path
from struct import unpack_from
from typing import Any, cast

import olefile
import xlrd
from openpyxl.formula.tokenizer import Tokenizer
from openpyxl.utils.cell import range_boundaries
from xlrd.formula import FMLA_TYPE_CELL, decompile_formula


def _records(data: bytes, start: int = 0) -> Iterator[tuple[int, bytes]]:
    while start + 4 <= len(data):
        kind, size = unpack_from("<HH", data, start)
        end = start + 4 + size
        if end > len(data):
            return
        yield kind, data[start + 4 : end]
        start = end


class XlsFormulas:
    """Index formula presence lazily and decode only explicitly checked total cells."""

    def __init__(self, path: Path, book: xlrd.book.Book) -> None:
        self._path, self._book = path, book
        self._cells: dict[str, dict[tuple[int, int], bytes]] | None = None
        self._decoded: dict[tuple[str, int, int], str | None] = {}

    def _index(self) -> dict[str, dict[tuple[int, int], bytes]]:
        if self._cells is not None:
            return self._cells
        self._cells = {}
        try:
            with olefile.OleFileIO(str(self._path)) as archive:
                stream = "Workbook" if archive.exists("Workbook") else "Book"
                data = archive.openstream(stream).read()
            offsets = [
                unpack_from("<I", record)[0]
                for kind, record in _records(data)
                if kind == 0x85 and len(record) >= 6 and record[5] == 0
            ]
            for name, offset in zip(self._book.sheet_names(), offsets, strict=True):
                cells: dict[tuple[int, int], bytes] = {}
                for kind, record in _records(data, offset):
                    if kind == 0x0A:
                        break
                    if kind == 0x06 and len(record) >= 22:
                        row, col = unpack_from("<HH", record)
                        cells[row + 1, col + 1] = record
                self._cells[name] = cells
        except Exception:
            # This optional metadata proves absence only; unreadable metadata retains cached values.
            self._cells = {}
        return self._cells

    def contains(self, sheet: str, row: int, col: int) -> bool:
        return (row, col) in self._index().get(sheet, {})

    def formula(self, sheet: str, row: int, col: int) -> str | None:
        key = sheet, row, col
        if key not in self._decoded:
            record = self._index().get(sheet, {}).get((row, col))
            formula = None
            if record is not None:
                try:
                    size = unpack_from("<H", record, 20)[0]
                    decode = cast(Callable[..., str | None], decompile_formula)
                    text = decode(
                        self._book, record[22:], size, FMLA_TYPE_CELL, browx=row - 1, bcolx=col - 1
                    )
                    formula = "=" + text if text else None
                except Exception:
                    # Exotic/shared/invalid BIFF formulas are not proof of blank inputs.
                    formula = None
            self._decoded[key] = formula
        return self._decoded[key]


def formula_inputs_blank(
    formula: str | None, sheet: str, read: Callable[[str, int, int], Any]
) -> bool:
    """Only a top-level SUM of blank cell/range operands proves an absent total."""
    try:
        operands = _sum_operands(formula) if formula and formula.startswith("=") else []
        if not operands:
            return False
        for address in operands:
            reference = _reference(address, sheet)
            if reference is None:
                return False
            name, first_col, first_row, last_col, last_row = reference
            if (last_row - first_row + 1) * (last_col - first_col + 1) > 1_000_000:
                return False
            for row in range(first_row, last_row + 1):
                for col in range(first_col, last_col + 1):
                    if read(name, row, col) not in (None, ""):
                        return False
        return True
    except Exception:
        # Malformed formulas or unresolved references leave the source's cached number intact.
        return False


def _sum_operands(formula: str) -> list[str]:
    tokens = [token for token in Tokenizer(formula).items if token.type != "WHITE-SPACE"]
    if (
        len(tokens) < 3
        or (tokens[0].type, tokens[0].subtype, tokens[0].value.upper()) != ("FUNC", "OPEN", "SUM(")
        or (tokens[-1].type, tokens[-1].subtype) != ("FUNC", "CLOSE")
    ):
        return []
    operands = tokens[1:-1]
    if len(operands) % 2 != 1 or not all(
        (token.type, token.subtype, token.value) == ("SEP", "ARG", ",")
        if index % 2
        else (token.type, token.subtype) == ("OPERAND", "RANGE")
        for index, token in enumerate(operands)
    ):
        return []
    return [token.value for token in operands[::2]]


def _reference(address: str, sheet: str) -> tuple[str, int, int, int, int] | None:
    name, separator, cells = address.rpartition("!")
    name = name.strip("'").replace("''", "'") if separator else sheet
    cells = cells if separator else address
    if "[" in name:
        return None
    first_col, first_row, last_col, last_row = range_boundaries(cells)
    if None in (first_col, first_row, last_col, last_row):
        return None
    assert first_col is not None and first_row is not None
    assert last_col is not None and last_row is not None
    if not (1 <= first_row <= last_row <= 1_048_576 and 1 <= first_col <= last_col <= 16_384):
        return None
    return name, first_col, first_row, last_col, last_row
