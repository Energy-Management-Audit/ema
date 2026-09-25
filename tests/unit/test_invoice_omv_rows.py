"""Synthetic OMV annex and ANAF rows retain price evidence and isolate bad rows."""

from decimal import Decimal
from pathlib import Path

from ema.invoices.models import DocumentPage, EnergyCategory, InputDocument, IssueCode
from ema.invoices.parsers.omv_petrom_parser import OmvPetromInvoiceParser
from ema.invoices.parsers.omv_rows import anaf_rows, annex_rows, representative_period


def test_annex_rows_keep_quantity_price_and_ambiguity_count() -> None:
    page = DocumentPage(
        2,
        "Denumire servicii facturate\n"
        "1 Energie activa 01.01.2025 - 31.01.2025 1,5 MWh 100,00 150,00 28,50\n"
        "2 Energie reactiva capacitiva 01.01.2025 - 31.01.2025 3 MAH 6,00 1,14\n"
        "3 Total 01.01.2025 - 31.01.2025 1 MWh 1 1 1\n"
        "4 Energie activa 01.01.2025 - 31.01.2025 5 MWh bad price\n",
        (),
    )
    details, periods, unparsed = annex_rows(page)
    assert len(details) == len(periods) == 2
    assert unparsed == 1
    assert details[0].category is EnergyCategory.ACTIVE_ENERGY
    assert details[0].source_quantity == Decimal("1.5")
    assert details[0].normalized_quantity == Decimal("1500")
    assert details[0].net_value == Decimal("150")
    assert details[1].category is EnergyCategory.REACTIVE_CAPACITIVE
    assert details[1].normalized_unit == "kVArh"
    assert details[1].normalized_quantity == Decimal("3000")
    assert details[0].evidence.page_number == 2
    assert representative_period(periods)[0] == "01.01.2025 - 31.01.2025"


def test_anaf_rows_bind_site_period_and_article_price() -> None:
    page = DocumentPage(
        3,
        "Energie activa\n"
        "Cod articol furnizor\n"
        "MWH 1,5 - 19% 150,00\n"
        "PCE 100,00\n"
        "RS123456 01.01.2025 - 31.01.2025\n"
        "Cod articol furnizor\n"
        "RS999999 01.01.2025 - 31.01.2025",
        (),
    )
    locations = anaf_rows(page)
    first = locations["RS123456"]
    assert first.unparsed == 0
    assert first.details[0].category is EnergyCategory.ACTIVE_ENERGY
    assert first.details[0].source_unit == "MWH"
    assert first.details[0].source_unit_price == Decimal("100")
    assert first.periods[0][0].year == 2025
    assert locations["RS999999"].unparsed == 1
    assert not locations["RS999999"].details


def test_annex_parser_creates_one_draft_with_located_price() -> None:
    page = DocumentPage(
        1,
        "OMVPETROM\nAnexa factura fiscala nr. 123 din data de 01.02.2025\n"
        "POD: ABCDEF123\nDenumire servicii facturate\n"
        "1 Energie activa 01.01.2025 - 31.01.2025 1,5 MWh 100,00 150,00 28,50",
        (),
    )
    parser = OmvPetromInvoiceParser()
    document = InputDocument(Path("synthetic.pdf"), (page,))
    assert parser.recognizes(document)
    drafts = parser.parse(document)
    assert len(drafts) == 1
    assert drafts[0].fields["invoice_number"].value == "123"
    assert drafts[0].fields["location_identifier"].value == "ABCDEF123"
    assert drafts[0].price_details[0].net_value == Decimal("150")
    assert drafts[0].metadata["page_numbers"] == [1]


def test_anaf_parser_isolates_site_without_price_rows() -> None:
    page = DocumentPage(
        1,
        "OMV PETROM SA\nNumar factura: 123\nData factura: 01.02.2025\n"
        "Total pozitii factura\nEnergie activa\nCod articol furnizor\n"
        "MWH 1,5 - 19% 150,00\nPCE 100,00\nRS123456 01.01.2025 - 31.01.2025\n"
        "Cod articol furnizor\nRS999999 01.01.2025 - 31.01.2025",
        (),
    )
    parser = OmvPetromInvoiceParser()
    document = InputDocument(Path("synthetic.pdf"), (page,))
    assert parser.recognizes(document)
    drafts = parser.parse(document)
    assert {draft.fields["location_identifier"].value for draft in drafts} == {
        "RS123456",
        "RS999999",
    }
    by_site = {draft.fields["location_identifier"].value: draft for draft in drafts}
    assert len(by_site["RS123456"].price_details) == 1
    assert any(
        issue.code is IssueCode.INVALID_PRICE_RECONCILIATION for issue in by_site["RS999999"].issues
    )
