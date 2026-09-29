"""Synthetic cases for invoice ambiguity and duplicate protection."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from ema.clients.registry import create_client
from ema.core.workspace import Workspace
from ema.invoices import pipeline, run_batch
from ema.invoices.configuration.field_catalog import (
    BILLING_PERIOD,
    INVOICE_NUMBER,
    LOCATION_IDENTIFIER,
    METER_IDENTIFIER,
)
from ema.invoices.models import (
    DocumentPage,
    FieldStatus,
    FieldValue,
    InputDocument,
    InvoiceDraft,
    IssueCode,
)
from ema.invoices.parsers.eds_parser import EdsInvoiceParser
from ema.invoices.parsers.eds_prices import invoice_number_grammar, price_details
from ema.invoices.parsers.engie_parser import EngieInvoiceParser
from ema.invoices.parsers.normalization import parse_romanian_decimal
from ema.invoices.pipeline import ExtractInvoice, ProcessInvoiceFiles


def _page(text: str) -> DocumentPage:
    return DocumentPage(1, text, ())


def _eds_section(pod: str, quantity: str = "2,000") -> str:
    return (
        f"Denumire loc de consum: Loc {pod}\n"
        f"Cod de identificare loc de consum (POD): {pod}\n"
        f"Serie contor: METER-{pod}\n"
        "Energie activă 01.12.2025 - 31.12.2025\n"
        f"Energie activa MWH {quantity} 500,00 1.000,00 190,00 1.190,00"
    )


def test_eds_splits_two_complete_sections_on_one_page() -> None:
    document = InputDocument(
        Path("two-eds.pdf"),
        (_page(_eds_section("1001") + "\n" + _eds_section("1002")),),
    )
    drafts = EdsInvoiceParser().parse(document)
    assert [draft.fields[LOCATION_IDENTIFIER].value for draft in drafts] == ["1001", "1002"]
    assert [len(draft.price_details) for draft in drafts] == [1, 1]
    assert all(
        IssueCode.MULTIPLE_LOCATIONS not in [issue.code for issue in draft.issues]
        for draft in drafts
    )


def test_eds_ambiguous_sections_require_review_without_merged_prices() -> None:
    text = _eds_section("1001") + "\nCod de identificare loc de consum (POD): 1002"
    draft = EdsInvoiceParser().parse(InputDocument(Path("ambiguous-eds.pdf"), (_page(text),)))[0]
    assert not draft.is_exportable
    assert not draft.price_details
    assert draft.fields[LOCATION_IDENTIFIER].value is None
    assert IssueCode.MULTIPLE_LOCATIONS in [issue.code for issue in draft.issues]


def _engie_section(location: str, quantity: str) -> str:
    return (
        "Detalii factura seria ENG nr.123456\n"
        f"Cod tehnic: {location} SMI\n"
        "Perioada consum 01.02.2025 - 28.02.2025\n"
        "U.M Explicatii Cantitate energie Pret unitar Valoare fara TVA Total\n"
        f"kWh Energie Activa 01.02.2025 - 28.02.2025 {quantity} 0,50000 50,00 9,50 59,50"
    )


def test_engie_splits_two_complete_sections_on_one_page() -> None:
    text = (
        "ENGIE Romania S.A.\nFactura seria ENG nr.123456\n"
        + _engie_section("1001", "100,000")
        + "\n"
        + _engie_section("1002", "100,000")
    )
    drafts = EngieInvoiceParser().parse(InputDocument(Path("two-engie.pdf"), (_page(text),)))
    assert [draft.fields[LOCATION_IDENTIFIER].value for draft in drafts] == ["1001", "1002"]
    assert [len(draft.price_details) for draft in drafts] == [1, 1]


def test_engie_ambiguous_location_requires_review() -> None:
    text = _engie_section("1001", "100,000") + "\nCod tehnic: 1002 SMI"
    draft = EngieInvoiceParser().parse(InputDocument(Path("ambiguous-engie.pdf"), (_page(text),)))[
        0
    ]
    assert not draft.is_exportable
    assert not draft.price_details
    assert draft.fields[LOCATION_IDENTIFIER].value is None
    assert IssueCode.MULTIPLE_LOCATIONS in [issue.code for issue in draft.issues]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1.000", "1000"), ("1.234,56", "1234.56"), ("1,5", "1.5")],
)
def test_romanian_numbers(raw: str, expected: str) -> None:
    assert parse_romanian_decimal(raw) == Decimal(expected)


def test_invalid_separator_pattern_is_not_guessed() -> None:
    with pytest.raises(ValueError):
        parse_romanian_decimal("1.23.456")


def test_eds_grammar_requires_invoice_evidence() -> None:
    english = _page("Energie activa MWH 61.697 433.29 26,732.69 5,079.21 31,811.90")
    romanian = _page("Energie activa MWH 61,697 433,29 26.732,69 5.079,21 31.811,90")
    ambiguous = _page("Energie activa MWH 61.697 1.000 1.000 1.000 1.000")
    assert invoice_number_grammar((english,)) == "english"
    assert invoice_number_grammar((romanian,)) == "romanian"
    assert invoice_number_grammar((ambiguous,)) is None
    assert invoice_number_grammar((english, romanian)) is None
    assert price_details((english,), "english")[0][0].source_quantity == Decimal("61.697")
    assert price_details((romanian,), "romanian")[0][0].source_quantity == Decimal("61.697")
    draft = EdsInvoiceParser().parse(
        InputDocument(
            Path("ambiguous.pdf"),
            (
                _page(
                    "Denumire loc de consum: X\nCod de identificare loc de consum (POD): 1001\n"
                    "Serie contor: M1\n" + ambiguous.text
                ),
            ),
        )
    )[0]
    assert not draft.is_exportable
    assert any("Separatoarele numerice" in issue.message for issue in draft.issues)


def test_eds_contradicting_number_formats_require_review() -> None:
    text = (
        "Denumire loc de consum: X\n"
        "Cod de identificare loc de consum (POD): 1001\n"
        "Serie contor: M1\n"
        "Energie activa MWH 61.697 433.29 26,732.69 5,079.21 31,811.90\n"
        "Energie activa MWH 61,697 433,29 26.732,69 5.079,21 31.811,90"
    )
    draft = EdsInvoiceParser().parse(InputDocument(Path("conflicting.pdf"), (_page(text),)))[0]
    assert not draft.is_exportable
    assert not draft.price_details
    assert any("Separatoarele numerice" in issue.message for issue in draft.issues)


def test_eds_green_adjustment_uses_confirmed_english_grammar() -> None:
    text = (
        "ENERGY DISTRIBUTION SERVICES SRL\n"
        "Factura regularizare certificate verzi\n"
        "SERIA FEDS Nr. 12345\n"
        "1 Regularizare certificate verzi MWh 61.697 433.29 26,732.69 5,079.21 31,811.90"
    )
    draft = EdsInvoiceParser().parse(InputDocument(Path("green-adjustment.pdf"), (_page(text),)))[0]
    assert len(draft.price_details) == 1
    assert draft.price_details[0].source_quantity == Decimal("61.697")
    assert draft.price_details[0].net_value == Decimal("26732.69")


class _Reader:
    def read(self, path: Path) -> InputDocument:
        return InputDocument(path, (_page(path.read_text(encoding="utf-8")),))


class _Parser:
    supplier_name = "Synthetic supplier"
    layout_version = "1"
    document_type = "electricity_invoice"

    def recognizes(self, document: InputDocument) -> bool:
        return True

    def parse(self, document: InputDocument) -> list[InvoiceDraft]:
        value = document.pages[0].text
        fields = {
            INVOICE_NUMBER: FieldValue("INV-1", FieldStatus.EXTRACTED),
            LOCATION_IDENTIFIER: FieldValue("POD-1", FieldStatus.EXTRACTED),
            BILLING_PERIOD: FieldValue("01.01.2025 - 31.01.2025", FieldStatus.EXTRACTED),
            "active_energy": FieldValue(Decimal(value), FieldStatus.EXTRACTED),
        }
        return [InvoiceDraft(document.path.stem, document.path.name, self.supplier_name, fields)]


def test_identity_duplicate_with_different_file_bytes(tmp_path: Path) -> None:
    first, second = tmp_path / "first.pdf", tmp_path / "second.pdf"
    first.write_text("1", encoding="utf-8")
    second.write_text("1.0", encoding="utf-8")
    result = ProcessInvoiceFiles(_Reader(), ExtractInvoice([_Parser()])).execute([first, second])
    assert [outcome.status.value for outcome in result.outcomes] == ["exportable", "duplicate"]
    assert result.outcomes[1].drafts == ()


def test_identity_conflict_blocks_both_invoices(tmp_path: Path) -> None:
    first, second = tmp_path / "first.pdf", tmp_path / "second.pdf"
    first.write_text("1", encoding="utf-8")
    second.write_text("2", encoding="utf-8")
    result = ProcessInvoiceFiles(_Reader(), ExtractInvoice([_Parser()])).execute([first, second])
    assert [outcome.status.value for outcome in result.outcomes] == [
        "requires_review",
        "requires_review",
    ]
    assert all(IssueCode.CONFLICTING_INVOICE in outcome.issue_codes for outcome in result.outcomes)
    assert not result.exportable


def test_multimeter_duplicate_with_missing_meter_value_is_safe(tmp_path: Path) -> None:
    class MultiMeterParser(_Parser):
        def parse(self, document: InputDocument) -> list[InvoiceDraft]:
            drafts = super().parse(document)
            base = drafts[0]
            missing = dict(base.fields)
            missing[METER_IDENTIFIER] = FieldValue(None, FieldStatus.MISSING)
            present = dict(base.fields)
            present[METER_IDENTIFIER] = FieldValue("METER-1", FieldStatus.EXTRACTED)
            return [
                InvoiceDraft(
                    f"{document.path.stem}-{suffix}",
                    document.path.name,
                    base.supplier,
                    fields,
                )
                for suffix, fields in (("missing", missing), ("present", present))
            ]

    first, second = tmp_path / "first.pdf", tmp_path / "second.pdf"
    first.write_text("1", encoding="utf-8")
    second.write_text("1.0", encoding="utf-8")
    result = ProcessInvoiceFiles(_Reader(), ExtractInvoice([MultiMeterParser()])).execute(
        [first, second]
    )
    assert [outcome.status.value for outcome in result.outcomes] == [
        "requires_review",
        "duplicate",
    ], [outcome.metadata.technical_detail for outcome in result.outcomes]


def test_dedupe_error_marks_both_documents_for_review(tmp_path: Path, monkeypatch) -> None:
    first, second = tmp_path / "first.pdf", tmp_path / "second.pdf"
    first.write_text("1", encoding="utf-8")
    second.write_text("1.0", encoding="utf-8")

    def fail_dedupe(*args, **kwargs):
        raise TypeError("synthetic dedupe failure")

    monkeypatch.setattr(pipeline, "_same_invoice", fail_dedupe)
    result = ProcessInvoiceFiles(_Reader(), ExtractInvoice([_Parser()])).execute([first, second])
    assert [outcome.status.value for outcome in result.outcomes] == [
        "requires_review",
        "requires_review",
    ]
    assert all("synthetic dedupe failure" in outcome.reason for outcome in result.outcomes)


def test_supplier_suffix_variants_share_canonical_identity(tmp_path: Path) -> None:
    class SupplierSuffixParser(_Parser):
        supplier_name = "MET"

        def parse(self, document: InputDocument) -> list[InvoiceDraft]:
            draft = super().parse(document)[0]
            printed_name = document.path.stem
            return [
                InvoiceDraft(
                    draft.document_id,
                    draft.source_filename,
                    printed_name,
                    draft.fields,
                )
            ]

    first, second = tmp_path / "MET ROMANIA ENERGY SA.pdf", tmp_path / "MET ROMANIA ENERGY S.A..pdf"
    first.write_text("1", encoding="utf-8")
    second.write_text("1.0", encoding="utf-8")
    result = ProcessInvoiceFiles(_Reader(), ExtractInvoice([SupplierSuffixParser()])).execute(
        [first, second]
    )
    assert [outcome.status.value for outcome in result.outcomes] == ["exportable", "duplicate"]


def test_unreadable_source_does_not_abort_run_batch(tmp_path: Path) -> None:
    missing = tmp_path / "missing.pdf"
    corrupt = tmp_path / "corrupt.pdf"
    corrupt.write_bytes(b"not a PDF")
    ws = Workspace(tmp_path / "workspace")
    create_client(ws, "Synthetic", "12345678")
    result = run_batch(ws, "12345678", [missing, corrupt])
    assert [outcome["status"] for outcome in result.outcomes] == ["failed", "failed"]
    assert result.outcomes[0]["metadata"]["technical_detail"]
    assert result.workbook is None
