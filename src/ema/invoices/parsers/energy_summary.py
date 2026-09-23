from __future__ import annotations

from decimal import Decimal

from ema.invoices.configuration.field_catalog import (
    ACTIVE_ENERGY,
    ACTIVE_ENERGY_LOSSES,
    ACTIVE_ENERGY_LOSSES_PRICE,
    ACTIVE_ENERGY_LOSSES_UNIT,
    ACTIVE_ENERGY_PRICE,
    ACTIVE_ENERGY_UNIT,
    GREEN_CERTIFICATES,
    GREEN_CERTIFICATES_PRICE,
    REACTIVE_CAPACITIVE,
    REACTIVE_CAPACITIVE_PRICE,
    REACTIVE_INDUCTIVE,
    REACTIVE_INDUCTIVE_PRICE,
)
from ema.invoices.models import (
    EnergyCategory,
    FieldStatus,
    FieldValue,
    PriceDetail,
)

_FIELD_MAPPINGS = (
    (
        EnergyCategory.ACTIVE_ENERGY,
        ACTIVE_ENERGY,
        ACTIVE_ENERGY_PRICE,
        ACTIVE_ENERGY_UNIT,
        "kWh",
    ),
    (
        EnergyCategory.ACTIVE_ENERGY_LOSSES,
        ACTIVE_ENERGY_LOSSES,
        ACTIVE_ENERGY_LOSSES_PRICE,
        ACTIVE_ENERGY_LOSSES_UNIT,
        "kWh",
    ),
    (
        EnergyCategory.REACTIVE_CAPACITIVE,
        REACTIVE_CAPACITIVE,
        REACTIVE_CAPACITIVE_PRICE,
        None,
        "kVArh",
    ),
    (
        EnergyCategory.REACTIVE_INDUCTIVE,
        REACTIVE_INDUCTIVE,
        REACTIVE_INDUCTIVE_PRICE,
        None,
        "kVArh",
    ),
    (
        EnergyCategory.GREEN_CERTIFICATES,
        GREEN_CERTIFICATES,
        GREEN_CERTIFICATES_PRICE,
        None,
        "kWh",
    ),
)


def add_energy_summary_fields(
    fields: dict[str, FieldValue],
    details: list[PriceDetail],
) -> None:
    """Populate the stable Excel fields from lossless supplier price details."""

    for category, quantity_field, price_field, unit_field, unit in _FIELD_MAPPINGS:
        matching = [detail for detail in details if detail.category is category]
        evidence = tuple(detail.evidence for detail in matching)
        quantity = sum((detail.normalized_quantity for detail in matching), Decimal(0))
        net_value = sum((detail.net_value for detail in matching), Decimal(0))
        weighted_price = net_value / quantity if quantity else Decimal(0)
        message = None if matching else "Category absent on source invoice; exported as zero."
        fields[quantity_field] = FieldValue(
            value=quantity,
            status=FieldStatus.EXTRACTED,
            evidence=evidence,
            message=message,
        )
        fields[price_field] = FieldValue(
            value=weighted_price,
            status=FieldStatus.EXTRACTED,
            evidence=evidence,
            message=message,
        )
        if unit_field:
            fields[unit_field] = FieldValue(value=unit, status=FieldStatus.EXTRACTED)
