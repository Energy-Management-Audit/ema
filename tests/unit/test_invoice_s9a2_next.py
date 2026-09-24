"""Synthetic Next Energy parser regressions ported from the legacy suite."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from s9a2_batch_support import assert_parser_batch_exportable

from ema.invoices.configuration.field_catalog import (
    ACTIVE_ENERGY,
    ACTIVE_ENERGY_PRICE,
    BILLING_PERIOD,
    CLIENT_NAME,
    CLIENT_TAX_ID,
    GREEN_CERTIFICATES,
    GREEN_CERTIFICATES_PRICE,
    INVOICE_DATE,
    INVOICE_NUMBER,
    LOCATION_IDENTIFIER,
)
from ema.invoices.models import DocumentPage, InputDocument, IssueCode, TextBlock
from ema.invoices.parsers.next_energy_parser import NextEnergyInvoiceParser
from ema.invoices.pipeline import ExtractInvoice


def make_page(number: int = 1, text: str = "Invoice sample text", blocks=()) -> DocumentPage:
    prefix = "Client: Exemplu Industrie SRL\nCUI client: RO99887766\n"
    return DocumentPage(number, f"{prefix}{text}", blocks)


def make_document(filename: str = "invoice.pdf", pages=None) -> InputDocument:
    return InputDocument(Path(filename), pages or (make_page(),))


def test_next_extracts_rvx_invoice_metadata_location_and_price_rows() -> None:
    document = make_document(
        "1001.pdf",
        pages=(
            make_page(
                text="""
NEXT ENERGY PARTNERS S.R.L.
Factura fiscala seria TWEE nr. 1001 din data de 15.05.2024
Perioada de facturare: 01.04.2024 - 30.04.2024
Loc de consum: APM000000000000001
1 Energie activa (01.04.2024 - 30.04.2024) MWh 2.0000 100.00 200.00 38.00
2 Plafonare Energie Electrica (01.04.2024 - 30.04.2024) MWh -2.0000 50.00 -100.00 -19.00
7 CV certificate verzi (01.04.2024 - 30.04.2024) MWh 2.0000 20.00 40.00 8.00
""",
            ),
        ),
    )

    draft = NextEnergyInvoiceParser().parse(document)[0]

    assert draft.fields[INVOICE_NUMBER].value == "TWEE-1001"
    assert draft.fields[INVOICE_DATE].value == date(2024, 5, 15)
    assert draft.fields[BILLING_PERIOD].value == "01.04.2024 - 30.04.2024"
    assert draft.fields[LOCATION_IDENTIFIER].value == "APM000000000000001"
    assert draft.fields[CLIENT_NAME].value == "Exemplu Industrie SRL"
    assert draft.fields[CLIENT_TAX_ID].value == "RO99887766"
    assert draft.fields[ACTIVE_ENERGY].value == Decimal("2000.0")
    assert draft.fields[ACTIVE_ENERGY_PRICE].value == Decimal("200.00") / Decimal("2000.0")
    assert draft.fields[GREEN_CERTIFICATES].value == Decimal("2000.0")
    assert draft.fields[GREEN_CERTIFICATES_PRICE].value == Decimal("40.00") / Decimal("2000.0")
    assert len(draft.price_details) == 3
    assert draft.is_exportable


def test_next_extracts_legacy_advance_and_requires_missing_location_review() -> None:
    document = make_document(
        "advance.pdf",
        pages=(
            make_page(
                text="""
NEXT ENERGY PARTNERS S.R.L.
FACTURA nr. TWEU-1002
Data emitere: 08.03.2023
Perioada facturare: Martie 2023
1 Avans energie electrica pret de baza MWh 2.0000 100.00 200.00 38.00
5 CV certificate verzi - avans MWh 2.0000 20.00 40.00 8.00
""",
            ),
        ),
    )

    draft = NextEnergyInvoiceParser().parse(document)[0]

    assert draft.fields[INVOICE_NUMBER].value == "TWEU-1002"
    assert draft.fields[INVOICE_DATE].value == date(2023, 3, 8)
    assert draft.fields[BILLING_PERIOD].value == "01.03.2023 - 31.03.2023"
    assert draft.fields[ACTIVE_ENERGY].value == Decimal("2000.0")
    assert draft.fields[LOCATION_IDENTIFIER].requires_review
    assert [issue.code for issue in draft.issues] == [IssueCode.MISSING_LOCATION_IDENTIFIER]


def test_next_classifies_storno_advance_as_negative_active_energy() -> None:
    document = make_document(
        "storno-advance.pdf",
        pages=(
            make_page(
                text=(
                    "NEXT ENERGY PARTNERS S.R.L.\n"
                    "FACTURA nr. TWE-1003\n"
                    "Data emitere: 07.08.2023\n"
                    "Perioada facturare: 01.08.2023 - 31.08.2023\n"
                    "Loc de consum: APM000000000000001\n"
                    "1 Storno AVANS VANZARE EXEMPLU CLIENT SRL 50% conform "
                    "MWh -2.0000 100.00 -200.00 -38.00\n"
                ),
            ),
        ),
    )

    draft = NextEnergyInvoiceParser().parse(document)[0]

    assert draft.fields[ACTIVE_ENERGY].value == Decimal("-2000.0")
    assert draft.fields[ACTIVE_ENERGY_PRICE].value == Decimal("-200.00") / Decimal("-2000.0")
    assert draft.price_details[0].category.value == "active_energy"
    assert draft.is_exportable


def test_next_extracts_numar_factura_layout() -> None:
    document = make_document(
        "advance-june.pdf",
        pages=(
            make_page(
                text="""
NEXT ENERGY PARTNERS S.R.L.
FACTURA
Numar factura: TWEU-1004
Data factura: 08.06.2023
Perioada facturare: 01.06.2023 - 30.06.2023
1 Avans energie electrica pret de baza MWh 2.0000 100.00 200.00 38.00
""",
            ),
        ),
    )

    draft = NextEnergyInvoiceParser().parse(document)[0]

    assert draft.fields[INVOICE_NUMBER].value == "TWEU-1004"
    assert draft.fields[INVOICE_DATE].value == date(2023, 6, 8)
    assert draft.fields[BILLING_PERIOD].value == "01.06.2023 - 30.06.2023"


def test_next_extracts_current_efactura_block_rows_without_inventing_pod() -> None:
    blocks = (
        TextBlock("RO eFactura", 0, 0, 10, 10),
        TextBlock("TWEE-1005\nNr. factura", 0, 10, 10, 20),
        TextBlock("Data emitere\n2024-10-12", 0, 20, 10, 30),
        TextBlock(
            "19.00\nEnergie activa (01.09.2024 - 30.09.2024)\n1\nRON\n1\n"
            "2.000\n200.00\nMWH\n100\n19.00\nCV certificate verzi "
            "(01.09.2024 - 30.09.2024)\n2\nRON\n1\n2.000\n40.00\n"
            "MWH\n20.00\n",
            0,
            30,
            10,
            40,
        ),
    )
    document = make_document(
        "efactura.pdf",
        pages=(make_page(text="NEXT ENERGY PARTNERS S.R.L.", blocks=blocks),),
    )

    draft = NextEnergyInvoiceParser().parse(document)[0]

    assert draft.fields[INVOICE_NUMBER].value == "TWEE-1005"
    assert draft.fields[INVOICE_DATE].value == date(2024, 10, 12)
    assert draft.fields[BILLING_PERIOD].value == "01.09.2024 - 30.09.2024"
    assert len(draft.price_details) == 2
    assert draft.fields[LOCATION_IDENTIFIER].requires_review
    assert [issue.code for issue in draft.issues] == [IssueCode.MISSING_LOCATION_IDENTIFIER]


def test_next_extracts_early_efactura_rotated_block_rows() -> None:
    blocks = (
        TextBlock("RO eFactura", 0, 0, 10, 10),
        TextBlock("TWEE-1006\nNr. factura", 0, 10, 10, 20),
        TextBlock("Data emitere\n2024-07-12", 0, 20, 10, 30),
        TextBlock(
            "100\nRON\n1\n2.000\nMWH\n19.00\n200.00\nEnergie activa (01.06.2024 - 30.06.2024)\n1\n",
            0,
            30,
            10,
            40,
        ),
    )
    document = make_document(
        "early-efactura.pdf",
        pages=(make_page(text="NEXT ENERGY PARTNERS S.R.L.", blocks=blocks),),
    )

    draft = NextEnergyInvoiceParser().parse(document)[0]

    assert draft.fields[ACTIVE_ENERGY].value == Decimal("2000")
    assert len(draft.price_details) == 1
    assert not any(issue.code is IssueCode.INVALID_PRICE_RECONCILIATION for issue in draft.issues)


def test_next_blocks_export_when_price_row_does_not_reconcile() -> None:
    document = make_document(
        pages=(
            make_page(
                text="""
NEXT ENERGY PARTNERS S.R.L.
FACTURA nr. TWEE-1007
Data emitere: 10.04.2023
Perioada facturare: 01.03.2023 - 31.03.2023
Loc de consum: APM000000000000001
1 Energie activa MWh 10.0000 100.0000 500.00 95.00
""",
            ),
        )
    )

    draft = NextEnergyInvoiceParser().parse(document)[0]

    assert not draft.is_exportable
    assert any(issue.code is IssueCode.INVALID_PRICE_RECONCILIATION for issue in draft.issues)


def test_next_recognizes_next_energy_without_claiming_other_suppliers() -> None:
    parser = NextEnergyInvoiceParser()

    assert parser.recognizes(
        make_document(pages=(make_page(text="NEXT ENERGY PARTNERS S.R.L. factura"),))
    )
    assert not parser.recognizes(make_document(pages=(make_page(text="Other supplier factura"),)))


def test_next_energy_invoice_becomes_exportable_after_batch_confirmation(tmp_path: Path) -> None:
    document = make_document(
        "next-synthetic.pdf",
        pages=(
            make_page(
                text="""
NEXT ENERGY PARTNERS S.R.L.
FACTURA nr. TWEE-1008
Data emitere: 08.03.2024
Perioada de facturare: 01.02.2024 - 29.02.2024
Loc de consum: APM000000000000001
1 Energie activa MWh 1.0000 100.0000 100.00 19.00
"""
            ),
        ),
    )
    assert_parser_batch_exportable(tmp_path, NextEnergyInvoiceParser(), document)


def test_unknown_supplier_remains_unsupported_with_review_issue() -> None:
    extracted = ExtractInvoice([]).execute_with_parser(
        make_document(pages=(make_page(text="UNSUPPORTED ENERGY factura"),))
    )

    assert extracted.parser is None
    assert extracted.drafts[0].issues[0].code is IssueCode.UNSUPPORTED_SUPPLIER
    assert not extracted.drafts[0].is_exportable
