"""Number presentation used by the approved PIEE table prototype."""

from __future__ import annotations


def prototype_number(value: float | int, decimals: int, *, grouping: bool = True) -> str:
    rendered = f"{value:{',' if grouping else ''}.{decimals}f}"
    return rendered.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
