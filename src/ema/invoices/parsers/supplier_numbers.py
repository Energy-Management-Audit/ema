"""Parse the two numeric conventions present in imported supplier invoices."""

from decimal import Decimal

from ema.invoices.parsers.normalization import parse_english_decimal, parse_romanian_decimal


def parse_supplier_decimal(raw: str) -> Decimal:
    """Select the printed decimal separator by the last punctuation mark."""
    value = raw.strip().replace("\u00a0", " ")
    comma = value.rfind(",")
    dot = value.rfind(".")
    if comma >= 0 and dot >= 0:
        if comma > dot:
            return parse_romanian_decimal(value)
        return parse_english_decimal(value)
    if comma >= 0:
        return parse_romanian_decimal(value)
    return parse_english_decimal(value)
