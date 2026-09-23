"""Romanian presentation of document numbers; stored values stay untouched."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, localcontext


def format_number(
    value: float | int,
    decimals: int,
    unit: str | None = None,
    grouping: bool = True,
) -> str:
    if decimals < 0:
        raise ValueError("decimals must be nonnegative")
    decimal_value = Decimal(str(value))
    quantum = Decimal(1).scaleb(-decimals)
    precision = max(
        28, len(decimal_value.as_tuple().digits) + abs(decimal_value.adjusted()) + decimals + 2
    )
    rounded = _quantize(decimal_value, quantum, precision)
    if rounded.is_zero():
        rounded = abs(rounded)
    raw = f"{rounded:{',' if grouping else ''}.{decimals}f}"
    result = raw.replace(",", "\u0000").replace(".", ",").replace("\u0000", ".")
    return f"{result} {unit}" if unit else result


def _quantize(value: Decimal, quantum: Decimal, precision: int) -> Decimal:
    with localcontext() as context:
        context.prec = precision
        return value.quantize(quantum, rounding=ROUND_HALF_UP)
