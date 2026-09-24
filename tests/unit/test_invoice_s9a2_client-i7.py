"""Synthetic Getica and Electric Planners parser regressions."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from s9a2_batch_support import assert_parser_batch_exportable

from ema.invoices.configuration.field_catalog import (
    ACTIVE_ENERGY,
    BILLING_PERIOD,
    CLIENT_NAME,
    GREEN_CERTIFICATES,
    INVOICE_DATE,
    INVOICE_NUMBER,
    LOCATION_IDENTIFIER,
    METER_IDENTIFIER,
)
from ema.invoices.models import (
    DocumentPage,
    FieldStatus,
    InputDocument,
)
from ema.invoices.parsers.CLIENT-I7_supplier_parser import (
    ElectricPlannersInvoiceParser,
    GeticaInvoiceParser,
)


def _document(*texts: str) -> InputDocument:
    return InputDocument(
        Path("invoice.pdf"),
        tuple(DocumentPage(index, text, ()) for index, text in enumerate(texts, start=1)),
    )


def test_CLIENT-I7_getica_splits_locations_and_uses_only_location_price_rows() -> None:
    document = _document(
        """
Nr. factura: BZGETEE23 1001
Data emitere: 15.02.2023
GETICA 95 COM S.R.L.
Client: EXEMPLU CLIENT S.A.
CUI client: RO99887766
Perioada facturare: 28.12.2022 - 31.01.2023
""",
        """
Loc (POD: 123456789012345678)
1 Pret de baza energie electrica [M] MWh 10 100 1,000 190
2 Certificate verzi conform Legii 220/2008 [M] MWh 10 20 200 38
""",
        """
Alt loc (POD: 123456789012345679)
3 Pret de baza energie electrica [M] MWh 5 100 500 95
""",
    )

    drafts = GeticaInvoiceParser().parse(document)

    assert len(drafts) == 2
    assert drafts[0].fields[INVOICE_NUMBER].value == "BZGETEE23 1001"
    assert drafts[0].fields[BILLING_PERIOD].value == "28.12.2022 - 31.01.2023"
    assert drafts[0].fields[LOCATION_IDENTIFIER].value == "123456789012345678"
    assert drafts[0].fields[CLIENT_NAME].value == "EXEMPLU CLIENT S.A."
    assert drafts[0].fields[ACTIVE_ENERGY].value == Decimal("10000")
    assert drafts[0].fields[GREEN_CERTIFICATES].value == Decimal("10000")
    assert all(draft.is_exportable for draft in drafts)


def test_CLIENT-I7_electric_planners_preserves_same_pod_with_distinct_meters() -> None:
    header = """
FACTURĂ ENERGIE ELECTRICĂ
SERIA ELEC Nr. 1001
Data emitere: 15.04.2024
ELECTRIC PLANNERS SRL
Client: EXEMPLU CLIENT SA
CUI client: RO99887766
Perioada de facturare: 01.03.2024 - 31.03.2024
"""
    first = """
Cod de identificare loc de consum (POD): 123456789012345678
Serie contor: 10001
Storno prezumat energie activa (TG inclus) MWH -2.000 100.000 \
-200.00 -38.00 -238.00
"""
    second = """
Cod de identificare loc de consum (POD): 123456789012345678
Serie contor: 10002
Energie activă 01.03.2024-31.03.2024 1 2 3
Energie activa (TG inclus) MWH 5 100 500 95 595
Certificate verzi MWH 5 20 100 19 119
"""

    drafts = ElectricPlannersInvoiceParser().parse(_document(header, first, second))

    assert len(drafts) == 2
    assert drafts[0].fields[INVOICE_NUMBER].value == "ELEC 1001"
    assert drafts[0].fields[METER_IDENTIFIER].value == "10001"
    assert drafts[1].fields[METER_IDENTIFIER].value == "10002"
    assert drafts[1].fields[ACTIVE_ENERGY].value == Decimal("5000")
    assert drafts[1].fields[GREEN_CERTIFICATES].value == Decimal("5000")
    assert drafts[0].fields[INVOICE_DATE].value == date(2024, 4, 15)
    assert all(draft.is_exportable for draft in drafts)


def test_CLIENT-I7_electric_planners_exports_client_level_advance_without_inventing_pod() -> None:
    document = _document(
        """
FACTURĂ ENERGIE ELECTRICĂ (AVANS)
SERIA ELEC Nr. 1002
Data emitere: 29.04.2024
ELECTRIC PLANNERS SRL
Client: EXEMPLU CLIENT SA
CUI client: RO99887766
Perioada de facturare: 01.05.2024 - 15.05.2024
Factura curentă fără TVA: 1.000,00 RON
[OCR horizontal-strip alternatives]
AVANS ENERGIE TOTAL DE PLATĂ DATA SCADENȚĂ
ELECTRICĂ (MWh) CU TVA (RON)
10,00 1.000,00 14.05.2024
"""
    )

    draft = ElectricPlannersInvoiceParser().parse(document)[0]

    assert draft.fields[LOCATION_IDENTIFIER].value is None
    assert draft.fields[LOCATION_IDENTIFIER].status.value == "not_provided"
    assert draft.fields[ACTIVE_ENERGY].value == Decimal("10000")
    assert draft.price_details[0].source_unit_price == Decimal("100")
    assert draft.is_exportable


def test_CLIENT-I7_electric_planners_recovers_wrapped_quantity_from_printed_net_and_price() -> None:
    document = _document(
        """
FACTURĂ ENERGIE ELECTRICĂ
SERIA ELEC Nr. 1003
Data emitere: 17.05.2024
ELECTRIC PLANNERS SRL
Client: EXEMPLU CLIENT SA
CUI client: RO99887766
Perioada de facturare: 01.04.2024 - 30.04.2024
""",
        """
Cod de identificare loc de consum (POD): 123456789012345680
Serie contor: 10003
Energie activa (TG inclus) MWH 5 100 500 95 595
Certificate verzi MWH 000 20 100 19 119
En. reactiv capacitiva kVArh 000 1 10 2 12
""",
    )

    draft = ElectricPlannersInvoiceParser().parse(document)[0]
    certificate = next(
        detail for detail in draft.price_details if detail.category.value == "green_certificates"
    )
    capacitive = next(
        detail for detail in draft.price_details if detail.category.value == "reactive_capacitive"
    )

    assert certificate.source_quantity == Decimal("5")
    assert capacitive.source_quantity == Decimal("10")
    assert "cantitate recuperată" in certificate.description
    assert draft.is_exportable


def test_getica_invoice_becomes_exportable_after_batch_confirmation(tmp_path: Path) -> None:
    document = _document(
        """
Nr. factura: BZGETEE23 1001
Data emitere: 15.02.2023
GETICA 95 COM S.R.L.
Client: EXEMPLU CLIENT S.A.
CUI client: RO99999999
Perioada facturare: 28.12.2022 - 31.01.2023
Loc (POD: 123456789012345678)
1 Pret de baza energie electrica [M] MWh 10 100 1,000 190
"""
    )
    assert_parser_batch_exportable(tmp_path, GeticaInvoiceParser(), document)


def test_getica_missing_client_name_is_supplied_by_batch_identity(tmp_path: Path) -> None:
    document = _document(
        """
Nr. factura: BZGETEE23 1002
Data emitere: 15.02.2023
GETICA 95 COM S.R.L.
Perioada facturare: 28.12.2022 - 31.01.2023
Loc (POD: 123456789012345681)
1 Pret de baza energie electrica [M] MWh 10 100 1,000 190
"""
    )
    identity_document = _document(
        """
Nr. factura: BZGETEE23 1003
Data emitere: 15.02.2023
GETICA 95 COM S.R.L.
Client: EXEMPLU CLIENT S.A.
CUI client: RO99999999
Perioada facturare: 28.12.2022 - 31.01.2023
Loc (POD: 123456789012345682)
1 Pret de baza energie electrica [M] MWh 10 100 1,000 190
"""
    )
    parser = GeticaInvoiceParser()
    draft = parser.parse(document)[0]
    assert draft.fields[CLIENT_NAME].status is FieldStatus.MISSING
    assert_parser_batch_exportable(
        tmp_path,
        parser,
        document,
        companion_documents=(identity_document,),
    )


def test_electric_planners_invoice_becomes_exportable_after_batch_confirmation(
    tmp_path: Path,
) -> None:
    document = _document(
        """
FACTURĂ ENERGIE ELECTRICĂ
SERIA ELEC Nr. 1001
Data emitere: 15.04.2024
ELECTRIC PLANNERS SRL
Client: EXEMPLU CLIENT SA
CUI client: RO99887766
Perioada de facturare: 01.03.2024 - 31.03.2024
""",
        """
Cod de identificare loc de consum (POD): 123456789012345678
Serie contor: 10002
Energie activa (TG inclus) MWH 5 100 500 95 595
Certificate verzi MWH 5 20 100 19 119
""",
    )
    assert_parser_batch_exportable(tmp_path, ElectricPlannersInvoiceParser(), document)
