from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FieldKind(StrEnum):
    TEXT = "text"
    DATE = "date"
    DECIMAL = "decimal"


@dataclass(frozen=True)
class FieldDefinition:
    field_id: str
    label: str
    required: bool
    kind: FieldKind
    unit: str | None = None


INVOICE_NUMBER = "invoice_number"
INVOICE_DATE = "invoice_date"
BILLING_PERIOD = "billing_period"
LOCATION_IDENTIFIER = "location_identifier"
METER_IDENTIFIER = "meter_identifier"
CONSUMPTION_PERIOD = "consumption_period"
CLIENT_NAME = "client_name"
CLIENT_TAX_ID = "client_tax_id"
ACTIVE_ENERGY = "active_energy"
ACTIVE_ENERGY_UNIT = "active_energy_unit"
ACTIVE_ENERGY_PRICE = "active_energy_price"
ACTIVE_ENERGY_LOSSES = "active_energy_losses"
ACTIVE_ENERGY_LOSSES_UNIT = "active_energy_losses_unit"
ACTIVE_ENERGY_LOSSES_PRICE = "active_energy_losses_price"
REACTIVE_CAPACITIVE = "reactive_capacitive"
REACTIVE_CAPACITIVE_PRICE = "reactive_capacitive_price"
REACTIVE_INDUCTIVE = "reactive_inductive"
REACTIVE_INDUCTIVE_PRICE = "reactive_inductive_price"
GREEN_CERTIFICATES = "green_certificates"
GREEN_CERTIFICATES_PRICE = "green_certificates_price"


FIELD_CATALOG: tuple[FieldDefinition, ...] = (
    FieldDefinition(INVOICE_NUMBER, "Numar factura", True, FieldKind.TEXT),
    FieldDefinition(INVOICE_DATE, "Data factura", True, FieldKind.DATE),
    FieldDefinition(BILLING_PERIOD, "Perioada facturata", True, FieldKind.TEXT),
    FieldDefinition(
        LOCATION_IDENTIFIER,
        "Identificator loc de consum",
        True,
        FieldKind.TEXT,
    ),
    FieldDefinition(METER_IDENTIFIER, "Serie contor", False, FieldKind.TEXT),
    FieldDefinition(
        CONSUMPTION_PERIOD,
        "Perioada de consum segment",
        False,
        FieldKind.TEXT,
    ),
    FieldDefinition(CLIENT_NAME, "Denumire client", True, FieldKind.TEXT),
    FieldDefinition(CLIENT_TAX_ID, "CUI/CIF client", False, FieldKind.TEXT),
    FieldDefinition(ACTIVE_ENERGY, "Energie Activa", False, FieldKind.DECIMAL, "kWh"),
    FieldDefinition(ACTIVE_ENERGY_UNIT, "U.M. energie activa", False, FieldKind.TEXT),
    FieldDefinition(
        ACTIVE_ENERGY_PRICE,
        "Pret mediu ponderat fara TVA (lei/kWh)",
        False,
        FieldKind.DECIMAL,
        "lei/kWh",
    ),
    FieldDefinition(
        ACTIVE_ENERGY_LOSSES,
        "Pierderi energie activa",
        False,
        FieldKind.DECIMAL,
        "kWh",
    ),
    FieldDefinition(
        ACTIVE_ENERGY_LOSSES_UNIT,
        "U.M. pierderi",
        False,
        FieldKind.TEXT,
    ),
    FieldDefinition(
        ACTIVE_ENERGY_LOSSES_PRICE,
        "Pret mediu ponderat pierderi fara TVA (lei/kWh)",
        False,
        FieldKind.DECIMAL,
        "lei/kWh",
    ),
    FieldDefinition(
        REACTIVE_CAPACITIVE,
        "Energie Reactiva Capacitiva (kVArh)",
        False,
        FieldKind.DECIMAL,
        "kVArh",
    ),
    FieldDefinition(
        REACTIVE_CAPACITIVE_PRICE,
        "Pret mediu ponderat capacitiv fara TVA (lei/kVArh)",
        False,
        FieldKind.DECIMAL,
        "lei/kVArh",
    ),
    FieldDefinition(
        REACTIVE_INDUCTIVE,
        "Energie Reactiva Inductiva (kVArh)",
        False,
        FieldKind.DECIMAL,
        "kVArh",
    ),
    FieldDefinition(
        REACTIVE_INDUCTIVE_PRICE,
        "Pret mediu ponderat inductiv fara TVA (lei/kVArh)",
        False,
        FieldKind.DECIMAL,
        "lei/kVArh",
    ),
    FieldDefinition(
        GREEN_CERTIFICATES,
        "Certificate verzi platite",
        False,
        FieldKind.DECIMAL,
        "kWh",
    ),
    FieldDefinition(
        GREEN_CERTIFICATES_PRICE,
        "Pret mediu ponderat certificate fara TVA (lei/kWh)",
        False,
        FieldKind.DECIMAL,
        "lei/kWh",
    ),
)

FIELD_BY_ID = {definition.field_id: definition for definition in FIELD_CATALOG}
