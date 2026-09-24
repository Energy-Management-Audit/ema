from __future__ import annotations

import re
import unicodedata
from datetime import date

from ema.invoices.models import InputDocument


def is_efactura(document: InputDocument) -> bool:
    return any(
        "ro efactura" in plain_text(block.text) for page in document.pages for block in page.blocks
    )


def document_text(document: InputDocument) -> str:
    return "\n".join(
        (page.text + "\n" + "\n".join(block.text for block in page.blocks))
        for page in document.pages
    )


def normalize_invoice_number(value: str) -> str:
    compact = re.sub(r"\s+", "", value).upper()
    match = re.fullmatch(r"([A-Z]+)-?(\d+)", compact)
    return f"{match.group(1)}-{match.group(2)}" if match else compact


def format_period(start: date, end: date) -> str:
    return f"{start:%d.%m.%Y} - {end:%d.%m.%Y}"


def plain_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return " ".join(
        "".join(character for character in normalized if not unicodedata.combining(character))
        .casefold()
        .split()
    )
