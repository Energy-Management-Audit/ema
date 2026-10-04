"""A Fill fact's value as its source writes it: numbers, years and the unit beside the number."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from ema.audit.catalogue_labels import FACT_TYPES
from ema.core.errors import EmaError
from ema.core.review.models import Derivation

NUMBER = re.compile(r"(?<!\w)[+-]?\d[\d . ]*(?:,\d+)?(?!\w)")
_UNIT = re.compile(r"\s*([^\W\d_]+)")
# A unit a quote may state instead of its fact's own, with the factor to the fact's unit.
CONVERSIONS: dict[tuple[str, str], Decimal] = {("MWp", "kWp"): Decimal(1000)}


def number(text: str) -> Decimal | None:
    """A number as a source writes it: `1.234,5`, `1 234,5` or `1234.5`."""
    raw = text.strip().replace(" ", "").replace(" ", "")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        result = Decimal(raw)
    except InvalidOperation:
        return None
    return result if result.is_finite() else None


def typed(key: str, value: str | int | float) -> str | int | Decimal:
    """The value in its fact's type: a typed fact's number or year, else the text as given."""
    kind = FACT_TYPES[key][0] if key in FACT_TYPES else None
    if kind is None:
        return value if isinstance(value, str) else Decimal(str(value))
    found = number(value) if isinstance(value, str) else Decimal(str(value))
    if kind == "year" and found is not None and found == int(found) and 1900 < found < 2100:
        return int(found)
    if kind == "number" and found is not None:
        return found
    raise EmaError("fact_type", "Tipul faptului nu este valid.", key)


def number_in_quote(value: object, quote: str) -> bool:
    try:
        wanted = Decimal(str(value))
    except InvalidOperation:
        return False
    return any(number(match.group()) == wanted for match in NUMBER.finditer(quote))


def in_unit(
    key: str, value: Decimal, quote: str, evidence: str
) -> tuple[Decimal, Derivation | None]:
    """The value in its fact's unit, read from the unit the quote writes right after the number.

    The fact's own unit is kept as is; a convertible one is converted with its derivation; any
    other unit, or none, is rejected: "1 MWp" is never recorded as 1 kWp. A value the quote
    writes with two different units is ambiguous and rejected too.
    """
    unit = FACT_TYPES[key][1]
    written = {
        found.group(1)
        for match in NUMBER.finditer(quote)
        if number(match.group()) == value and (found := _UNIT.match(quote, match.end()))
    }
    if unit is None:
        return value, None
    if len(written) > 1:
        raise EmaError("value_unverified", "Numărul apare cu unităţi diferite în fragment.", key)
    if unit in written:
        return value, None
    for (source, target), factor in CONVERSIONS.items():
        if target == unit and source in written:
            derivation = Derivation(
                formula_id=f"unit.{source}_to_{target}", inputs=[evidence], factor_version="none"
            )
            return value * factor, derivation
    raise EmaError("value_unverified", "Unitatea nu apare lângă număr în fragment.", key)
