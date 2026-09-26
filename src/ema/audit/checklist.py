"""Read the numbered request list from Necesar info by labels, never cell addresses."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ema.core.errors import EmaError
from ema.core.office.sheets import open_book

_NUMBER = re.compile(r"^\s*(1[0-3]|[1-9])\s*[.)]?\s*$")


@dataclass(frozen=True)
class ChecklistItem:
    number: int
    text: str
    sheet: str
    row: int


def read_checklist(path: Path) -> tuple[ChecklistItem, ...]:
    book = open_book(path)
    try:
        matches = [name for name in book.sheet_names if "diverse" in name.casefold()]
        if len(matches) != 1:
            raise EmaError("checklist_sheet", "Foaia diverse lipseşte sau este ambiguă.", "")
        sheet = book.sheet(matches[0])
        found: dict[int, ChecklistItem] = {}
        for row in range(1, sheet.max_row + 1):
            for col in range(1, sheet.max_col):
                value = sheet.value(row, col).value
                if isinstance(value, int | float) and not isinstance(value, bool):
                    label = str(int(value)) if float(value).is_integer() else str(value)
                else:
                    label = str(value) if value is not None else ""
                match = _NUMBER.fullmatch(label)
                if not match:
                    continue
                number = int(match.group(1))
                if number in found:
                    raise EmaError(
                        "checklist_duplicate",
                        "Lista de documente are numere repetate.",
                        str(number),
                    )
                text = sheet.value(row, col + 1).value
                if not isinstance(text, str) or not text.strip():
                    raise EmaError(
                        "checklist_text", "Descrierea documentului lipseşte.", str(number)
                    )
                found[number] = ChecklistItem(number, text.strip(), sheet.name, row)
        if set(found) != set(range(1, 14)):
            raise EmaError(
                "checklist_count",
                "Lista de documente nu are 13 poziţii.",
                ",".join(str(n) for n in sorted(found)),
            )
        return tuple(found[number] for number in range(1, 14))
    finally:
        book.close()
