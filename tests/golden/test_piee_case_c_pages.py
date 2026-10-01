"""Word page render and paired visual review of PIEE case C."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pdfplumber
import pypdfium2 as pdfium
import pytest
from PIL import Image, ImageDraw
from tests.golden.cases import case_path

from conftest import artifacts_path
from ema.core.config import Settings
from ema.core.office.word_api import word_automation, word_available
from ema.piee.compose import compose_draft
from ema.piee.dataset import load

pytestmark = [pytest.mark.golden, pytest.mark.word]


def _page_image(page: pdfium.PdfPage, width: int) -> Image.Image:
    scale = width / page.get_width()
    return page.render(scale=scale).to_pil().convert("RGB")


def _contact_sheets(reference: Path, draft: Path, directory: Path) -> None:
    with pdfium.PdfDocument(reference) as expected, pdfium.PdfDocument(draft) as actual:
        for index in range(max(len(expected), len(actual))):
            left = _page_image(expected[index], 560) if index < len(expected) else None
            right = _page_image(actual[index], 560) if index < len(actual) else None
            height = max(
                left.height if left is not None else 0, right.height if right is not None else 0
            )
            sheet = Image.new("RGB", (1160, height + 44), "white")
            draw = ImageDraw.Draw(sheet)
            draw.text((12, 12), f"Reference page {index + 1}", fill="black")
            draw.text((592, 12), f"Ema page {index + 1}", fill="black")
            if left is not None:
                sheet.paste(left, (0, 44))
            if right is not None:
                sheet.paste(right, (580, 44))
            sheet.save(directory / f"pair-{index + 1:03d}.png")


def test_case_c_word_pages_keep_each_caption_with_its_figure(tmp_path: Path) -> None:
    settings = Settings()
    if not word_available(settings):
        pytest.skip(f"Word unavailable at {settings.word_path}")
    final = case_path("piee-case-c", "final")
    data = load(
        2025,
        case_path("piee-case-c", "anexa"),
        None,
        case_path("piee-case-c", "prelucrare"),
        final,
    )
    draft = tmp_path / "draft.docx"
    status = compose_draft(data, artifacts_path("s8", "base"), draft, date(2026, 10, 1))
    assert status.final_ready
    word = word_automation(settings)
    word.open_check(draft)
    directory = artifacts_path("piee-case-c", "pages")
    directory.mkdir(parents=True, exist_ok=True)
    reference_pdf, draft_pdf = directory / "reference.pdf", directory / "draft.pdf"
    word.render_pdf(final, reference_pdf)
    word.render_pdf(draft, draft_pdf)
    _contact_sheets(reference_pdf, draft_pdf, directory)
    with pdfplumber.open(draft_pdf) as pdf:
        captions = [
            (page_number, line["top"])
            for page_number, page in enumerate(pdf.pages, 1)
            for line in page.extract_text_lines()
            if re.match(r"^Fig\.\s*(?:nr\.\s*)?\d+", line["text"], re.I)
        ]
    assert len(captions) == 39
    assert all(top >= 150 for _, top in captions), [
        page_number for page_number, top in captions if top < 150
    ]
