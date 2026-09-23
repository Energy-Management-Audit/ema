from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ema.invoices.configuration.field_catalog import (
    ACTIVE_ENERGY,
    ACTIVE_ENERGY_LOSSES,
    ACTIVE_ENERGY_LOSSES_PRICE,
    ACTIVE_ENERGY_PRICE,
    BILLING_PERIOD,
    CONSUMPTION_PERIOD,
    GREEN_CERTIFICATES,
    GREEN_CERTIFICATES_PRICE,
    INVOICE_DATE,
    INVOICE_NUMBER,
    LOCATION_IDENTIFIER,
    METER_IDENTIFIER,
    REACTIVE_CAPACITIVE,
    REACTIVE_CAPACITIVE_PRICE,
    REACTIVE_INDUCTIVE,
    REACTIVE_INDUCTIVE_PRICE,
)
from ema.invoices.models import InvoiceDraft

SUMMARY_SHEET = "Centralizator"
DETAIL_SHEET = "Detalii preturi"

SUMMARY_COLUMNS = (
    (INVOICE_NUMBER, "Numar factura"),
    (INVOICE_DATE, "Data factura"),
    (BILLING_PERIOD, "Perioada facturata"),
    (LOCATION_IDENTIFIER, "Identificator loc de consum"),
    (METER_IDENTIFIER, "Serie contor"),
    (CONSUMPTION_PERIOD, "Perioada de consum segment"),
    (ACTIVE_ENERGY, "Cantitate energie activa"),
    (None, "U.M. energie activa"),
    (ACTIVE_ENERGY_PRICE, "Pret unitar fara TVA energie activa"),
    (None, "Valoare totala fara TVA energie activa (lei)"),
    (ACTIVE_ENERGY_LOSSES, "Pierderi energie activa"),
    (None, "U.M."),
    (ACTIVE_ENERGY_LOSSES_PRICE, "Pret mediu ponderat pierderi fara TVA (lei/kWh)"),
    (REACTIVE_CAPACITIVE, "Energie Reactiva Capacitiva (kVArh)"),
    (REACTIVE_CAPACITIVE_PRICE, "Pret mediu ponderat capacitiv fara TVA (lei/kVArh)"),
    (REACTIVE_INDUCTIVE, "Energie Reactiva Inductiva (kVArh)"),
    (REACTIVE_INDUCTIVE_PRICE, "Pret mediu ponderat inductiv fara TVA (lei/kVArh)"),
    (GREEN_CERTIFICATES, "Cantitate certificate verzi"),
    (None, "U.M. certificate verzi"),
    (GREEN_CERTIFICATES_PRICE, "Pret unitar fara TVA certificate verzi"),
    (None, "Valoare totala fara TVA certificate verzi (lei)"),
)

DETAIL_HEADERS = (
    "Fisier sursa",
    "Furnizor",
    "Numar factura",
    "Identificator loc de consum",
    "Serie contor",
    "Perioada de consum segment",
    "Categorie",
    "Descriere sursa",
    "Cantitate sursa",
    "U.M. sursa",
    "Pret unitar sursa fara TVA",
    "Cantitate normalizata",
    "U.M. normalizata",
    "Pret normalizat fara TVA",
    "Valoare fara TVA",
    "Pagina",
    "Fragment sursa",
    "Draft ID",
)

DETAIL_CATEGORY_COLUMN = "G"
DETAIL_SOURCE_QUANTITY_COLUMN = "I"
DETAIL_NORMALIZED_QUANTITY_COLUMN = "L"
DETAIL_NET_VALUE_COLUMN = "O"
DETAIL_DRAFT_ID_COLUMN = "R"

SUMMARY_QUANTITY_COLUMNS = {
    7: "active_energy",
    11: "active_energy_losses",
    14: "reactive_capacitive",
    16: "reactive_inductive",
    18: "green_certificates",
}

SUMMARY_PRICE_COLUMNS = {
    9: "active_energy",
    13: "active_energy_losses",
    15: "reactive_capacitive",
    17: "reactive_inductive",
    20: "green_certificates",
}

SUMMARY_SOURCE_UNIT_COLUMNS = {
    8: "active_energy",
    19: "green_certificates",
}

SUMMARY_VALUE_COLUMNS = {
    10: "active_energy",
    21: "green_certificates",
}

SOURCE_BASIS_CATEGORIES = frozenset({"active_energy", "green_certificates"})

SUMMARY_QUANTITY_FORMAT = "#,##0.000;[Red]-#,##0.000;0"
SUMMARY_PRICE_FORMAT = "0.000000;[Red]-0.000000;0.000000"
SUMMARY_VALUE_FORMAT = "#,##0.00;[Red]-#,##0.00;0.00"
DETAIL_NUMBER_FORMAT = "#,##0.000000;[Red]-#,##0.000000;0"


@dataclass(frozen=True)
class SummaryBasis:
    quantity_detail_column: str
    unit: str
    unique_unit_price: Decimal | None


def summary_basis(invoice: InvoiceDraft, category: str) -> SummaryBasis:
    details = [detail for detail in invoice.price_details if detail.category.value == category]
    if not details:
        return SummaryBasis(DETAIL_NORMALIZED_QUANTITY_COLUMN, "", Decimal("0"))

    source_units = {_display_unit(detail.source_unit) for detail in details}
    if len(source_units) == 1:
        prices = {detail.source_unit_price for detail in details}
        return SummaryBasis(
            DETAIL_SOURCE_QUANTITY_COLUMN,
            next(iter(source_units)),
            next(iter(prices)) if len(prices) == 1 else None,
        )

    normalized_units = {_display_unit(detail.normalized_unit) for detail in details}
    normalized_prices = {detail.normalized_unit_price for detail in details}
    unit = next(iter(normalized_units)) if len(normalized_units) == 1 else "unitati mixte"
    return SummaryBasis(
        DETAIL_NORMALIZED_QUANTITY_COLUMN,
        unit,
        next(iter(normalized_prices)) if len(normalized_prices) == 1 else None,
    )


def summary_quantity_formula(
    category: str,
    detail_last_row: int,
    draft_id_cell: str,
    quantity_detail_column: str = DETAIL_NORMALIZED_QUANTITY_COLUMN,
) -> str:
    return (
        f"SUMIFS('{DETAIL_SHEET}'!${quantity_detail_column}$2:"
        f"${quantity_detail_column}${detail_last_row},"
        f"'{DETAIL_SHEET}'!${DETAIL_DRAFT_ID_COLUMN}$2:"
        f"${DETAIL_DRAFT_ID_COLUMN}${detail_last_row},{draft_id_cell},"
        f"'{DETAIL_SHEET}'!${DETAIL_CATEGORY_COLUMN}$2:"
        f'${DETAIL_CATEGORY_COLUMN}${detail_last_row},"{category}")'
    )


def summary_net_formula(category: str, detail_last_row: int, draft_id_cell: str) -> str:
    return (
        f"SUMIFS('{DETAIL_SHEET}'!${DETAIL_NET_VALUE_COLUMN}$2:"
        f"${DETAIL_NET_VALUE_COLUMN}${detail_last_row},"
        f"'{DETAIL_SHEET}'!${DETAIL_DRAFT_ID_COLUMN}$2:"
        f"${DETAIL_DRAFT_ID_COLUMN}${detail_last_row},{draft_id_cell},"
        f"'{DETAIL_SHEET}'!${DETAIL_CATEGORY_COLUMN}$2:"
        f'${DETAIL_CATEGORY_COLUMN}${detail_last_row},"{category}")'
    )


def summary_price_formula(
    category: str,
    detail_last_row: int,
    draft_id_cell: str,
    quantity_detail_column: str = DETAIL_NORMALIZED_QUANTITY_COLUMN,
) -> str:
    quantity_sum = summary_quantity_formula(
        category,
        detail_last_row,
        draft_id_cell,
        quantity_detail_column,
    )
    net_sum = summary_net_formula(category, detail_last_row, draft_id_cell)
    return f'=IF({quantity_sum}=0,IF({net_sum}=0,0,"N/A"),{net_sum}/{quantity_sum})'


def summary_value_formula(category: str, detail_last_row: int, draft_id_cell: str) -> str:
    return f"={summary_net_formula(category, detail_last_row, draft_id_cell)}"


def _display_unit(value: str) -> str:
    return {
        "kwh": "kWh",
        "mwh": "MWh",
        "kvarh": "kVArh",
        "mvarh": "MVArh",
    }.get(value.casefold(), value)
