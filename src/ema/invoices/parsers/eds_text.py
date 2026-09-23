from __future__ import annotations

import re
import unicodedata


def plain_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return " ".join(
        "".join(character for character in normalized if not unicodedata.combining(character))
        .casefold()
        .split()
    )


def primary_text(value: str) -> str:
    return value.split("[OCR sparse-layout alternatives]", 1)[0]


def normalized_ocr_text(value: str) -> str:
    text = primary_text(value)
    return re.sub(
        r"(?<!\d)(\d{2})[.,](\d{2})[.,](\d{4})(?!\d)",
        r"\1.\2.\3",
        text,
    )
