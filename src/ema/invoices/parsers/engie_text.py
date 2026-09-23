from __future__ import annotations

import unicodedata


def plain_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return " ".join(
        "".join(character for character in normalized if not unicodedata.combining(character))
        .casefold()
        .replace("ã", "a")
        .split()
    )
