"""PDF text, positions and supervised local OCR."""

from __future__ import annotations

import io
import subprocess
import unicodedata
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
    executable: Path,
    image: bytes,
    lang: str,
    timeout_s: float,
    psm: int,
    format_: str,
) -> str:
    try:
        result = subprocess.run(
            [
                str(executable),
                "stdin",
                "stdout",
                "--dpi",
                "200",
                "-l",
                lang,
                "--psm",
                str(psm),
                format_,
            ],
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
    alternatives: bool = False,
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
                if alternatives:
                    oriented = _run_tesseract(executable, png, lang, timeout_s, 1, "txt")
                    sparse = _run_tesseract(executable, png, lang, timeout_s, 11, "txt")
                    raw_text = _merge_ocr(raw_text, oriented, "[OCR auto-orientation alternatives]")
                    raw_text = _merge_ocr(raw_text, sparse, "[OCR sparse-layout alternatives]")
                    if "factur" in raw_text.casefold():
                        strips: list[str] = []
                        for strip in range(3):
                            height = page.get_height()
                            crop = (0, (2 - strip) * height / 3, 0, strip * height / 3)
                            strip_png = io.BytesIO()
                            render_page.render(scale=dpi / 72, crop=crop).to_pil().save(
                                strip_png, format="PNG"
                            )
                            strips.append(
                                _run_tesseract(
                                    executable, strip_png.getvalue(), lang, timeout_s, 6, "txt"
                                )
                            )
                        raw_text = _merge_strips(raw_text, strips)
                output.append(PageText(number, raw_text, _words(tsv, dpi), "ocr"))
    except EmaError:
        raise
    except Exception as exc:
        raise EmaError("pdf_render_failed", "Pagina PDF nu a putut fi randată.", str(exc)) from exc
    return output


def _comparison_key(line: str) -> str:
    decomposed = unicodedata.normalize("NFKD", line)
    return "".join(
        char.casefold() for char in decomposed if char.isalnum() and not unicodedata.combining(char)
    )


def _merge_ocr(primary: str, alternative: str, marker: str) -> str:
    lines = [line.strip() for line in primary.splitlines() if line.strip()]
    known = {_comparison_key(line) for line in lines}
    additions = [
        line.strip()
        for line in alternative.splitlines()
        if line.strip() and _comparison_key(line) not in known
    ]
    return "\n".join([*lines, *([marker, *additions] if additions else [])])


def _merge_strips(primary: str, strips: list[str]) -> str:
    lines = [line.strip() for line in primary.splitlines() if line.strip()]
    known = {" ".join(line.casefold().split()) for line in lines}
    additions: list[str] = []
    for strip in strips:
        for line in strip.splitlines():
            candidate = line.strip()
            key = " ".join(candidate.casefold().split())
            if key and key not in known:
                known.add(key)
                additions.append(candidate)
    return "\n".join(
        [*lines, *(["[OCR horizontal-strip alternatives]", *additions] if additions else [])]
    )
