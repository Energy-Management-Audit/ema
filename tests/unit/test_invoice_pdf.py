"""Synthetic PDF reader and OCR supervision checks."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ema.core import pdf
from ema.core.config import Settings
from ema.core.errors import EmaError


def _pdf(path: Path) -> Path:
    content = b"BT /F1 12 Tf 50 700 Td (Synthetic invoice) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    start = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    )
    path.write_bytes(data)
    return path


def _executable(path: Path, body: str, windows_body: str) -> Path:
    if sys.platform == "win32":
        path = path.with_suffix(".cmd")
        path.write_text(f"@echo off\n{windows_body}\n", encoding="utf-8")
        return path
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o700)
    return path


def test_text_keeps_page_and_word_position(tmp_path: Path) -> None:
    pages = pdf.text(_pdf(tmp_path / "invoice.pdf"))
    assert len(pages) == 1
    assert "Synthetic invoice" in pages[0].text
    assert pages[0].page == 1
    assert pages[0].words[0].x0 > 0


def test_ocr_uses_configured_child_and_word_boxes(tmp_path: Path) -> None:
    binary = _executable(
        tmp_path / "fake-tesseract",
        'cat >/dev/null\ncase "$*" in *tsv*) '
        'printf "text\\tleft\\ttop\\twidth\\theight\\nToken\\t20\\t30\\t10\\t12\\n" ;; '
        '*) printf "Token\\n" ;; esac',
        'more >nul\necho %* | findstr /C:"tsv" >nul\n'
        "if %errorlevel%==0 (echo text\tleft\ttop\twidth\theight& echo Token\t20\t30\t10\t12) "
        "else echo Token",
    )
    pages = pdf.ocr(_pdf(tmp_path / "invoice.pdf"), Settings(tesseract_path=binary))
    assert pages[0].text.strip() == "Token"
    assert pages[0].extraction_method == "ocr"
    assert pages[0].words[0].text == "Token"


def test_ocr_timeout_kills_child_and_error_keeps_stderr(tmp_path: Path) -> None:
    source = _pdf(tmp_path / "invoice.pdf")
    slow = _executable(
        tmp_path / "slow-tesseract",
        "cat >/dev/null\nsleep 2",
        'more >nul\npowershell -NoProfile -Command "Start-Sleep -Seconds 2"',
    )
    with pytest.raises(EmaError) as timeout:
        pdf.ocr(source, Settings(tesseract_path=slow), timeout_s=0.1)
    assert timeout.value.code == "ocr_timeout"

    bad = _executable(
        tmp_path / "bad-tesseract",
        'echo "synthetic stderr" >&2\nexit 3',
        "echo synthetic stderr 1>&2\nexit /b 3",
    )
    with pytest.raises(EmaError) as failure:
        pdf.ocr(source, Settings(tesseract_path=bad))
    assert failure.value.code == "ocr_failed"
    assert "synthetic stderr" in failure.value.detail
