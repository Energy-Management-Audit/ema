"""PDF text, positions and supervised local OCR."""

from __future__ import annotations

import io
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pdfplumber
import pypdfium2

from ema.core.config import Settings
from ema.core.errors import EmaError


@dataclass(frozen=True)
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True)
class PageText:
    page: int
    text: str
    words: tuple[Word, ...]
    extraction_method: str = "embedded"
    layout_text: str | None = None


def text(pdf: Path) -> list[PageText]:
    """Read embedded text with PDFium and word positions with pdfplumber."""
    try:
        with pypdfium2.PdfDocument(pdf) as document, pdfplumber.open(pdf) as positioned:
            pages: list[PageText] = []
            for index, page in enumerate(document):
                page_text = page.get_textpage().get_text_range()
                words = tuple(
                    Word(
                        str(word["text"]),
                        float(word["x0"]),
                        float(word["top"]),
                        float(word["x1"]),
                        float(word["bottom"]),
                    )
                    for word in positioned.pages[index].extract_words()
                )
                pages.append(
                    PageText(
                        index + 1,
                        page_text,
                        words,
                        layout_text=positioned.pages[index].extract_text(),
                    )
                )
            return pages
    except Exception as exc:
        raise EmaError("pdf_read_failed", "PDF-ul nu a putut fi citit.", str(exc)) from exc


def _run_tesseract(
    executable: Path, image: bytes, lang: str, timeout_s: float, psm: int, format_: str
) -> str:
    try:
        result = subprocess.run(
            [str(executable), "stdin", "stdout", "-l", lang, "--psm", str(psm), format_],
            input=image,
            capture_output=True,
            check=False,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise EmaError("ocr_timeout", "OCR-ul a depășit timpul permis.", str(exc)) from exc
    except OSError as exc:
        raise EmaError("ocr_start_failed", "OCR-ul nu a putut porni.", str(exc)) from exc
    if result.returncode:
        stderr = result.stderr.decode("utf-8", errors="replace")[:1000]
        raise EmaError("ocr_failed", "OCR-ul a eșuat.", stderr)
    return result.stdout.decode("utf-8", errors="replace")


def _words(tsv: str, dpi: int) -> tuple[Word, ...]:
    rows = tsv.splitlines()
    if not rows:
        return ()
    header = rows[0].split("\t")
    result: list[Word] = []
    for row in rows[1:]:
        columns = dict(zip(header, row.split("\t"), strict=False))
        token = columns.get("text", "").strip()
        if not token:
            continue
        try:
            x, y = float(columns["left"]), float(columns["top"])
            width, height = float(columns["width"]), float(columns["height"])
        except (KeyError, ValueError):
            continue
        scale = 72 / dpi
        result.append(Word(token, x * scale, y * scale, (x + width) * scale, (y + height) * scale))
    return tuple(result)


def ocr(
    pdf: Path,
    settings: Settings,
    *,
    lang: str = "ron+eng",
    timeout_s: float = 120,
    pages: set[int] | None = None,
) -> list[PageText]:
    executable = settings.tesseract_path
    if not executable.is_file():
        raise EmaError("ocr_unavailable", "Tesseract lipsește din configurație.", str(executable))
    dpi = 200
    output: list[PageText] = []
    try:
        with pypdfium2.PdfDocument(pdf) as document:
            for index, page in enumerate(document):
                number = index + 1
                if pages is not None and number not in pages:
                    continue
                image = io.BytesIO()
                render_page: Any = (
                    page  # PDFium's render stub types scale as int, but accepts float.
                )
                render_page.render(scale=dpi / 72).to_pil().save(image, format="PNG")
                png = image.getvalue()
                raw_text = _run_tesseract(executable, png, lang, timeout_s, 6, "txt")
                tsv = _run_tesseract(executable, png, lang, timeout_s, 6, "tsv")
                output.append(PageText(number, raw_text, _words(tsv, dpi), "ocr"))
    except EmaError:
        raise
    except Exception as exc:
        raise EmaError("pdf_render_failed", "Pagina PDF nu a putut fi randată.", str(exc)) from exc
    return output
