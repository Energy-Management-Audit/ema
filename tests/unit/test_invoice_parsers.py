"""Supplier parsers on invented invoice text and positioned blocks."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from ema.invoices.configuration.field_catalog import (
    ACTIVE_ENERGY,
    CLIENT_NAME,
    CONSUMPTION_PERIOD,
    INVOICE_DATE,
    INVOICE_NUMBER,
    LOCATION_IDENTIFIER,
)
from ema.invoices.models import DocumentPage, InputDocument, TextBlock
from ema.invoices.parsers.eds_parser import EdsInvoiceParser
from ema.invoices.parsers.engie_parser import EngieInvoiceParser
from ema.invoices.parsers.incompatible_parser import EngieEInvoiceCompanionParser
from ema.invoices.parsers.met_energy_parser import (
    MetElectricityInvoiceParser,
)
from ema.invoices.pipeline import ExtractInvoice, ProcessInvoiceFiles


def _page(number: int, text: str, *blocks: TextBlock) -> DocumentPage:
    return DocumentPage(number, text, blocks)


def test_eds_groups_pages_by_pod_and_keeps_period_evidence() -> None:
    header = _page(
        1,
        "FACTURĂ ENERGIE ELECTRICĂ\nSERIA FEDS Nr. 100001\n"
        "Data emitere: 15.01.2026\nENERGY DISTRIBUTION SERVICES SRL FABRICA EXEMPLU SA\n"
        "Perioada de facturare: 01.12.2025 - 31.12.2025",
        TextBlock("FABRICA EXEMPLU SA", 320, 200, 500, 220),
        TextBlock("Cod fiscal: RO1234567", 320, 220, 500, 240),
    )

    def detail(number: int, pod: str) -> DocumentPage:
        return _page(
            number,
            f"Denumire loc de consum: Hală\n"
            f"Cod de identificare loc de consum (POD): {pod}\n"
            "Serie contor: METER-1\nEnergie activă 01.12.2025 - 31.12.2025\n"
            "Energie activa (TG inclus) MWH 2,000 500,00 1.000,00 190,00 1.190,00",
        )

    document = InputDocument(
        Path("invented-eds.pdf"), (header, detail(2, "500000001"), detail(3, "500000002"))
    )
    drafts = EdsInvoiceParser().parse(document)
    assert len(drafts) == 2
    assert [draft.fields[LOCATION_IDENTIFIER].value for draft in drafts] == [
        "500000001",
        "500000002",
    ]
    assert all(draft.fields[ACTIVE_ENERGY].value == Decimal("2000") for draft in drafts)
    assert drafts[0].fields[CONSUMPTION_PERIOD].evidence[0].page_number == 2
    assert all(draft.is_exportable for draft in drafts)


def test_met_reads_positioned_e_factura_price_rows() -> None:
    blocks = (
        TextBlock("FABRICA EXEMPLU SA\nNume", 0, 0, 10, 10),
        TextBlock("RO1234567\nIdentificator", 0, 10, 10, 20),
        TextBlock("MET ROMANIA ENERGY SRL\nNume", 0, 20, 10, 30),
        TextBlock("RO7654321\nIdentificatorul TVA", 0, 30, 10, 40),
        TextBlock("EEFIN25 10001\nNr. factura", 0, 40, 10, 50),
        TextBlock("Data emitere\n2025-05-22", 0, 50, 10, 60),
        TextBlock("Perioada\n2025-04-01\n-\n2025-04-30\nMoneda facturii\nRON", 0, 60, 10, 70),
        TextBlock(
            "19\nPret de baza energie electrica fara Tg\n100001\nRON\n2.000\n"
            "1000.00\nMWH\n500.00\n",
            0,
            70,
            10,
            80,
        ),
    )
    document = InputDocument(
        Path("invented-met.pdf"),
        (
            _page(1, "MET ROMANIA ENERGY SRL RO eFactura Pret de baza energie electrica", *blocks),
            _page(
                2,
                "POD: 500000003",
                TextBlock("POD: 500000003", 0, 0, 10, 10),
            ),
        ),
    )
    draft = MetElectricityInvoiceParser().parse(document)[0]
    assert draft.fields[INVOICE_NUMBER].value == "EEFIN25 10001"
    assert draft.fields[INVOICE_DATE].value == date(2025, 5, 22)
    assert draft.fields[CLIENT_NAME].value == "FABRICA EXEMPLU SA"
    assert draft.fields[LOCATION_IDENTIFIER].value == "500000003"
    assert draft.fields[ACTIVE_ENERGY].value == Decimal("2000")
    assert len(draft.price_details) == 1


def test_engie_splits_locations_and_preserves_negative_adjustment() -> None:
    def page(
        number: int, location: str, quantity: str, net: str, vat: str, total: str
    ) -> DocumentPage:
        return _page(
            number,
            "Client: Exemplu Industrie SRL\nCUI client: RO12345678\n"
            "Anexa la factura fiscala seria ENG nr.123456 din data de 14.03.2025\n"
            "ENGIE Romania S.A.\nDetalii factura seria ENG nr.123456\n"
            "Data facturii: 14.03.2025\n"
            f"Cod autocitire: {location}\nCod loc consum distribuitor: 50001\n"
            f"Cod tehnic: 5000000000{location} SMI\n"
            "Perioada consum 01.02.2025 - 28.02.2025\n"
            "U.M Explicatii Cantitate energie Pret unitar Valoare fara TVA Total\n"
            f"kWh Energie Activa 01.02.2025 - 28.02.2025 {quantity} 0,50000 {net} {vat} {total}",
        )

    document = InputDocument(
        Path("invented-engie.pdf"),
        (
            page(1, "4001", "100,000", "50,00", "9,50", "59,50"),
            page(2, "4002", "-50,000", "-25,00", "-4,75", "-29,75"),
        ),
    )
    drafts = EngieInvoiceParser().parse(document)
    assert len(drafts) == 2
    assert drafts[0].fields[ACTIVE_ENERGY].value == Decimal("100")
    assert drafts[1].fields[ACTIVE_ENERGY].value == Decimal("-50")
    assert all(draft.is_exportable for draft in drafts)


def test_engie_companion_recognition_uses_labeled_client_identity() -> None:
    parser = EngieEInvoiceCompanionParser()
    document = InputDocument(
        Path("synthetic-engie-invoice.pdf"),
        (_page(1, "ENGIE Romania S.A.\nFactura eFactura\nClient: EXEMPLU CLIENT S.A."),),
    )
    without_client = InputDocument(
        Path("synthetic-engie-invoice.pdf"),
        (_page(1, "ENGIE Romania S.A.\nFactura eFactura"),),
    )

    assert parser.recognizes(document)
    assert not parser.recognizes(without_client)


def test_bad_file_does_not_stop_following_invoice(tmp_path: Path) -> None:
    broken = tmp_path / "broken.pdf"
    good = tmp_path / "good.pdf"
    broken.write_text("broken")
    good.write_text("good")

    class Reader:
        def read(self, path: Path) -> InputDocument:
            if path == broken:
                raise ValueError("synthetic unreadable PDF")
            return InputDocument(path, (_page(1, "unrecognized supplier"),))

    result = ProcessInvoiceFiles(Reader(), ExtractInvoice([EngieInvoiceParser()])).execute(
        [broken, good]
    )
    assert [outcome.status.value for outcome in result.outcomes] == ["failed", "requires_review"]
    assert "synthetic unreadable PDF" in (result.outcomes[0].metadata.technical_detail or "")
