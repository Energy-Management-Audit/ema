"""Synthetic Hidroelectrica and Enel/PPC parser regressions."""

from decimal import Decimal
from pathlib import Path

from s9a2_batch_support import assert_parser_batch_exportable

from ema.invoices.configuration.field_catalog import (
    ACTIVE_ENERGY,
    CLIENT_NAME,
    CONSUMPTION_PERIOD,
    LOCATION_IDENTIFIER,
    METER_IDENTIFIER,
)
from ema.invoices.models import (
    DocumentPage,
    EnergyCategory,
    InputDocument,
    PriceDetail,
    SourceEvidence,
)
from ema.invoices.parsers.hidroelectrica_ppc_parser import (
    EnelPpcInvoiceParser,
    HidroelectricaInvoiceParser,
    reconciles,
)


def _page(number: int, text: str) -> DocumentPage:
    return DocumentPage(number=number, text=text, blocks=())


def make_document(filename: str = "invoice.pdf", pages=None) -> InputDocument:
    return InputDocument(Path(filename), pages or ())


def test_hydro_hidroelectrica_preserves_aggregate_price_rows_with_composite_meter_id() -> None:
    document = make_document(
        "hidro.pdf",
        pages=(
            _page(
                1,
                """
Factură fiscală seria FX nr. 1001 din data de 28.10.2023
SPEEH HIDROELECTRICA SA
Client: EXEMPLU CLIENT SA
CIF: RO99887766
""",
            ),
            _page(
                2,
                "\n".join(
                    (
                        "Denumire loc de consum ____________________123456789012345678",
                        "Adresă loc de consum ____________________Strada Avram Iancu",
                        "POD ____________________123456789012345678",
                        "Denumire Servicii Facturate",
                        "Energie Activă factură curentă 1 150 kWh 1,00 "
                        "150,00 28,50 178,50 01.06.23-30.06.23",
                        "01.06.23 - 1,00 2,00 10001 EA kWh 100 100,00 100,00 30",
                        "01.06.23 - 3,00 4,00 ##10002 EA kWh 50,000 50,00 50,00 30",
                        "Detalii măsurări:",
                    )
                ),
            ),
        ),
    )

    draft = HidroelectricaInvoiceParser().parse(document)[0]

    assert draft.fields[LOCATION_IDENTIFIER].value == "123456789012345678"
    assert draft.fields[METER_IDENTIFIER].value == "10001 + 10002"
    assert draft.fields[CONSUMPTION_PERIOD].value == "01.06.2023 - 30.06.2023"
    assert draft.fields[ACTIVE_ENERGY].value == Decimal("150")
    assert draft.is_exportable


def test_hydro_enel_splits_printed_periods_and_derives_only_unprinted_unit_price() -> None:
    document = make_document(
        "enel.pdf",
        pages=(
            _page(
                1,
                """
Factură fiscală seria 23EI nr. 1002 din data de 31.07.2023
Client: EXEMPLU CLIENT SA
""",
            ),
            _page(
                2,
                """
Adresa loc consum Strada Exemplului, cod loc consum 1234567890
Cod punct de măsură EMO0000001
Serie contor: 10003
Energie activa 01.02.23 - 31.03.23 kWh 3.600 100,00 59
Denumire servicii facturate
4 01.02.23 - 31.03.23 100,00 kWh 1,00 100,00 19,00
6 01.02.23 - 28.02.23 -20,00 kWh -20,00 -4,00
""",
            ),
        ),
    )

    drafts = EnelPpcInvoiceParser().parse(document)

    assert len(drafts) == 2
    assert {draft.fields[CONSUMPTION_PERIOD].value for draft in drafts} == {
        "01.02.2023 - 31.03.2023",
        "01.02.2023 - 28.02.2023",
    }
    assert all(draft.fields[METER_IDENTIFIER].value == "10003" for draft in drafts)
    assert all(draft.fields[CLIENT_NAME].value == "EXEMPLU CLIENT SA" for draft in drafts)
    derived = next(
        detail
        for draft in drafts
        for detail in draft.price_details
        if "preț derivat" in detail.description
    )
    assert derived.net_value == Decimal("-20.00")
    assert all(draft.is_exportable for draft in drafts)


def test_hydro_hidroelectrica_accepts_sub_leu_printed_price_precision_difference() -> None:
    detail = PriceDetail(
        category=EnergyCategory.GREEN_CERTIFICATES,
        description="Certificate verzi",
        source_quantity=Decimal("1000"),
        source_unit="kWh",
        source_unit_price=Decimal("0.07191"),
        normalized_quantity=Decimal("1000"),
        normalized_unit="kWh",
        normalized_unit_price=Decimal("0.07191"),
        net_value=Decimal("71.91"),
        evidence=SourceEvidence(2, "source", "invoice price row"),
    )

    assert reconciles(detail)


def test_hidroelectrica_invoice_becomes_exportable_after_batch_confirmation(
    tmp_path: Path,
) -> None:
    document = make_document(
        "hydro-synthetic.pdf",
        pages=(
            _page(
                1,
                "Factură fiscală seria FX nr. 1001 din data de 28.10.2023\n"
                "SPEEH HIDROELECTRICA SA\nClient: EXEMPLU CLIENT SA\nCIF: RO99887766",
            ),
            _page(
                2,
                "Denumire loc de consum ____________________123456789012345678\n"
                "POD ____________________123456789012345678\nDenumire Servicii Facturate\n"
                "Energie Activă factură curentă 1 100 kWh 1,00 "
                "100,00 19,00 119,00 01.06.23-30.06.23\n"
                "01.06.23 - 1,00 2,00 10001 EA kWh 100 100,00 100,00 30\n"
                "Detalii măsurări:",
            ),
        ),
    )
    assert_parser_batch_exportable(tmp_path, HidroelectricaInvoiceParser(), document)


def test_enel_ppc_invoice_becomes_exportable_after_batch_confirmation(tmp_path: Path) -> None:
    document = make_document(
        "ppc-synthetic.pdf",
        pages=(
            _page(
                1,
                "Factură fiscală seria 23EI nr. 1002 din data de 31.07.2023\n"
                "Client: EXEMPLU CLIENT SA",
            ),
            _page(
                2,
                "Adresa loc consum Strada Exemplului, cod loc consum 1234567890\n"
                "Cod punct de măsură EMO0000001\nSerie contor: 10003\n"
                "Energie activa 01.02.23 - 31.03.23 kWh 3.600 100,00 59\n"
                "Denumire servicii facturate\n"
                "4 01.02.23 - 31.03.23 100,00 kWh 1,00 100,00 19,00\n"
                "6 01.02.23 - 28.02.23 -20,00 kWh -1,00 -4,00",
            ),
        ),
    )
    assert_parser_batch_exportable(tmp_path, EnelPpcInvoiceParser(), document)
