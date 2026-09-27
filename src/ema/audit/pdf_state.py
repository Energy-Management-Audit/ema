"""Classify PDF text availability before audit reading."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pypdfium2

from ema.core.errors import EmaError
from ema.core.pdf import text


def pdf_state(path: Path) -> Literal["protected", "scanned", "text"]:
    try:
        with pypdfium2.PdfDocument(path):
            pass
    except pypdfium2.PdfiumError as exc:
        if getattr(exc, "err_code", None) == 4:
            return "protected"
        raise EmaError("pdf_read_failed", "PDF-ul nu a putut fi citit.", str(exc)) from exc
    return "scanned" if all(not page.text.strip() for page in text(path)) else "text"
