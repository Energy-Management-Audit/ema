from __future__ import annotations

import unicodedata

from ema.invoices.models import InputDocument


def document_text(document: InputDocument) -> str:
    return "\n".join(
        page.text + "\n" + "\n".join(block.text for block in page.blocks) for page in document.pages
    )


def plain_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return " ".join(
        "".join(character for character in normalized if not unicodedata.combining(character))
        .casefold()
        .split()
    )
