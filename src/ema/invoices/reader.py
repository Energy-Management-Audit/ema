"""Adapt the shared PDF service to the ported parser document model."""

from __future__ import annotations

import re
from pathlib import Path

from ema.core import pdf
from ema.core.config import Settings
from ema.invoices.models import DocumentPage, InputDocument, TextBlock
from ema.invoices.parsers.met_layout import blocks as met_blocks

_DATE_RANGE = re.compile(r"\d{2}[.]\d{2}[.]\d{4}-\d{2}[.]\d{2}[.]\d{4}")


def _eds_period_rows(page: pdf.PageText) -> str:
    # pdfplumber can move the dates into a separate column. Their word boxes
    # still share the energy row's vertical position, as in the legacy reader.
    rows: list[str] = []
    for anchor in page.words:
        if not anchor.text.casefold().startswith("energie"):
            continue
        dates = (
            word.text
            for word in page.words
            if abs(word.y0 - anchor.y0) < 2.5 and word.x0 > anchor.x0
        )
        if date_range := next(
            (match.group(0) for token in dates if (match := _DATE_RANGE.fullmatch(token))), None
        ):
            rows.append(f"Energie {date_range.replace('-', ' - ')}")
    return "\n".join(rows)


class InvoiceDocumentReader:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def read(self, path: Path) -> InputDocument:
        pages = pdf.text(path)
        scans = {page.page for page in pages if sum(char.isalnum() for char in page.text) < 20}
        ocr_pages = (
            {page.page: page for page in pdf.ocr(path, self.settings, pages=scans)} if scans else {}
        )
        if scans and any("alive capital" in page.text.casefold() for page in ocr_pages.values()):
            ocr_pages = {
                page.page: page
                for page in pdf.ocr(path, self.settings, pages=scans, alternatives=True)
            }
        result: list[DocumentPage] = []
        is_met = "met romania energy" in " ".join(
            (page.layout_text or page.text).casefold() for page in pages
        )
        is_eds = "energy distribution services" in " ".join(
            (page.layout_text or page.text).casefold() for page in pages[:1]
        )
        for page in pages:
            selected = ocr_pages.get(page.page, page)
            page_text = selected.layout_text or selected.text
            if is_eds and selected.extraction_method == "embedded":
                period_rows = _eds_period_rows(selected)
                if period_rows:
                    page_text += f"\n{period_rows}"
            blocks = (
                met_blocks(selected)
                if is_met and selected.extraction_method == "embedded"
                else tuple(
                    TextBlock(word.text, word.x0, word.y0, word.x1, word.y1)
                    for word in selected.words
                )
            )
            result.append(
                DocumentPage(
                    number=selected.page,
                    text=page_text,
                    blocks=blocks,
                    extraction_method=selected.extraction_method,
                )
            )
        document = InputDocument(path, tuple(result))
        if not document.has_meaningful_text:
            raise ValueError("No readable invoice text could be extracted from the PDF.")
        return document
