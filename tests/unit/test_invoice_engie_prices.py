"""ENGIE table rows require reconciled values and preserve OCR evidence."""

from decimal import Decimal

from ema.invoices.models import DocumentPage, EnergyCategory
from ema.invoices.parsers.engie_prices import (
    EngiePriceMixin,
    _reconcile_financial_values,
    ocr_sparse_price_details,
)


def test_price_rows_deduplicate_and_refuse_bad_financial_arithmetic() -> None:
    line = "kWh Energie activa 10,00 2,00 20,00 3,80 23,80"
    page = DocumentPage(
        2,
        "Cantitate energie Pret unitar\n" + line + "\n" + line + "\n"
        "kWh Energie activa 10,00 2,00 30,00 3,80 33,80",
        (),
    )
    mixin = EngiePriceMixin()
    details = mixin._price_details(page)
    assert len(details) == 1
    assert details[0].category is EnergyCategory.ACTIVE_ENERGY
    assert details[0].net_value == Decimal("20")
    assert details[0].evidence.page_number == 2
    assert mixin._unparsed_price_row_count(page) == 1
    assert _reconcile_financial_values(
        Decimal("-10"), Decimal("2"), Decimal("20"), Decimal("3.8"), Decimal("23.8")
    ) == (Decimal("10"), Decimal("20"))


def test_sparse_ocr_row_requires_reconciled_financial_columns() -> None:
    page = DocumentPage(
        3,
        "[OCR sparse-layout alternatives]\n"
        "Explicatii\n"
        "kWh\nEnergie activa\n10,00\n2,00\n20,00\n3,80\n23,80\n"
        "kWh\nEnergie activa\n10,00\n2,00\n99,00\n3,80\n102,80",
        (),
        "ocr",
    )
    details = ocr_sparse_price_details(page)
    assert len(details) == 1
    assert details[0].net_value == Decimal("20")
    assert details[0].evidence.label == "OCR sparse-layout invoice price row"
    assert len(EngiePriceMixin()._price_details(page)) == 1


def test_unpriced_reactive_meter_reading_is_visible() -> None:
    page = DocumentPage(4, "Energie reactiva inductiva masurata 1.234", ())
    details = []
    EngiePriceMixin()._add_unpriced_reactive_readings((page,), details)
    assert len(details) == 1
    assert details[0].category is EnergyCategory.REACTIVE_INDUCTIVE
    assert details[0].source_quantity == Decimal("1234")
    assert details[0].net_value == 0
    assert details[0].evidence.label == "meter reading"
