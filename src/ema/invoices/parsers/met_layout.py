"""Restore MET's rotated e-Factura row order from positioned PDF words."""

from __future__ import annotations

import re

from ema.core.pdf import PageText, Word
from ema.invoices.models import TextBlock

_NUMBER = re.compile(r"[-−–]?[0-9][0-9.,]*")
_VAT = re.compile(r"(?:0|5|9|19|21)(?:[.,]0+)?%?")
_UNITS = {"MWH", "KWH", "MAH", "MVARH", "KVARH", "H87"}


def _row_block(anchor: Word, words: tuple[Word, ...]) -> TextBlock | None:
    row = sorted((word for word in words if abs(word.y0 - anchor.y0) < 2.5), key=lambda w: w.x0)
    right = [word for word in row if word.x0 > anchor.x0]
    units = [word for word in right if word.text.upper() in _UNITS]
    if not units:
        return None
    unit = units[0]
    prices = [word for word in row if word.x0 < anchor.x0 and _NUMBER.fullmatch(word.text)]
    quantities = [word for word in right if word.x0 < unit.x0 and _NUMBER.fullmatch(word.text)]
    vats = [word for word in right if word.x0 > unit.x0 and _VAT.fullmatch(word.text)]
    nets = [word for word in right if word.x0 > unit.x0 and _NUMBER.fullmatch(word.text)]
    if not (prices and quantities and vats and len(nets) >= 2):
        return None
    price = prices[-1]
    description = [word.text for word in row[1:] if word.x0 < price.x0]
    if not description:
        return None
    tokens = [
        vats[0].text,
        *description,
        description[-1],  # The legacy parser drops the code immediately before RON.
        anchor.text,
        quantities[0].text,
        nets[-1].text,
        unit.text,
        price.text,
    ]
    if "certificate" in " ".join(description).casefold():
        # A detached percentage and its leading digit follow this price in the
        # legacy column stream, so the parser joins them to that label.
        detached = [
            word.text
            for word in sorted(words, key=lambda candidate: candidate.y0)
            if word.x0 < anchor.x0
            and 8 <= word.y0 - anchor.y0 <= 25
            and (
                (word.text.isdigit() and len(word.text) == 1)
                or ("%" in word.text and _VAT.fullmatch(word.text))
            )
        ]
        if len(detached) == 2 and detached[0].isdigit() and detached[1].endswith("%"):
            tokens.extend(detached)
    return TextBlock("\n".join(tokens), row[0].x0, row[0].y0, row[-1].x1, row[-1].y1)


def blocks(page: PageText) -> tuple[TextBlock, ...]:
    """Provide the vertical token stream expected by the ported MET parser."""
    result = [TextBlock(page.layout_text or page.text, 0, 0, 0, 0)]
    for word in page.words:
        if word.text.upper() == "RON":
            block = _row_block(word, page.words)
            if block is not None:
                result.append(block)
    return tuple(result)
