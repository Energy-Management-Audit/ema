import io
import subprocess
from pathlib import Path
from typing import Any

import pypdfium2
import pytest
from tests.unit.test_invoice_pdf import _pdf

from ema.core import pdf
from ema.core.config import Settings
from ema.core.errors import EmaError
from ema.core.resources import resource_path


def test_bundled_tesseract_gets_tessdata_and_no_console(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, b"recognized", b"")

    monkeypatch.setattr(pdf.subprocess, "run", run)
    monkeypatch.setattr(pdf.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(pdf, "resource_path", tmp_path.joinpath)
    bundled = tmp_path / "tesseract" / "tesseract.exe"
    external = Path("/opt/homebrew/bin/tesseract")

    assert pdf._run_tesseract(bundled, b"image", "ron", 2, 6, "txt") == "recognized"
    assert calls[0][0][3:5] == ["--tessdata-dir", str(tmp_path / "tesseract" / "tessdata")]
    assert calls[0][1]["creationflags"] == 0x08000000
    assert pdf._run_tesseract(external, b"image", "ron", 2, 6, "txt") == "recognized"
    assert "--tessdata-dir" not in calls[1][0]


def _fake_run(
    monkeypatch: pytest.MonkeyPatch, text: str = "page text\n", tsv: str = "tsv rows\n"
) -> list[list[str]]:
    commands: list[list[str]] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        commands.append(args)
        if args[2] != "stdout":
            Path(args[2] + ".txt").write_bytes(text.encode())
            Path(args[2] + ".tsv").write_bytes(tsv.encode())
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(pdf.subprocess, "run", run)
    return commands


def test_page_run_is_one_invocation_with_both_renderers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands = _fake_run(monkeypatch)
    monkeypatch.setattr(pdf, "resource_path", tmp_path.joinpath)
    bundled = tmp_path / "tesseract" / "tesseract.exe"

    assert pdf._run_tesseract_page(bundled, b"image", "ron", 2) == ("page text\n", "tsv rows\n")
    assert len(commands) == 1
    command = commands[0]
    assert command[0] == str(bundled)
    assert command[1] == "stdin"
    assert command[3:5] == ["--tessdata-dir", str(tmp_path / "tesseract" / "tessdata")]
    assert command[5:] == ["--dpi", "200", "-l", "ron", "--psm", "6", "txt", "tsv"]

    pdf._run_tesseract_page(Path("/opt/homebrew/bin/tesseract"), b"image", "ron", 2)
    assert "--tessdata-dir" not in commands[1]


def test_page_run_error_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executable = Path("/opt/homebrew/bin/tesseract")

    def timeout(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired(args, 2)

    def missing(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise FileNotFoundError("no such binary")

    def failing(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(args, 3, b"", b"e" * 1500)

    for run, code in (
        (timeout, "ocr_timeout"),
        (missing, "ocr_start_failed"),
        (failing, "ocr_failed"),
    ):
        monkeypatch.setattr(pdf.subprocess, "run", run)
        with pytest.raises(EmaError) as error:
            pdf._run_tesseract_page(executable, b"image", "ron", 2)
        assert error.value.code == code
    assert error.value.detail == "e" * 1000


def test_page_run_matches_two_single_format_runs() -> None:
    settings = Settings()
    if not settings.tesseract_path.is_file():
        pytest.skip("Tesseract is not configured")
    with pypdfium2.PdfDocument(resource_path("selfcheck", "ocr-ro.pdf")) as document:
        page: Any = document[0]
        buffer = io.BytesIO()
        page.render(scale=200 / 72).to_pil().save(buffer, format="PNG", compress_level=1)
    png = buffer.getvalue()
    executable = settings.tesseract_path
    expected = (
        pdf._run_tesseract(executable, png, "ron+eng", 120, 6, "txt"),
        pdf._run_tesseract(executable, png, "ron+eng", 120, 6, "tsv"),
    )
    assert pdf._run_tesseract_page(executable, png, "ron+eng", 120) == expected


def _scan(tmp_path: Path) -> Path:
    return _pdf(tmp_path / "scan.pdf")


def _psm_runs(commands: list[list[str]]) -> list[tuple[str, str]]:
    return [(c[c.index("--psm") + 1], c[2]) for c in commands]


@pytest.mark.parametrize("text", ["plain\n", "Factura 1\n"])
def test_ocr_run_counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    commands = _fake_run(monkeypatch, text=text)
    settings = Settings(tesseract_path=tmp_path / "tesseract")
    settings.tesseract_path.write_bytes(b"")
    source = _scan(tmp_path)
    strips = 3 if "factur" in text.casefold() else 0

    pdf.ocr(source, settings)
    assert [psm for psm, _ in _psm_runs(commands)] == ["6"]

    commands.clear()
    base = {1: pdf.PageText(1, text, (pdf.Word("w", 1, 2, 3, 4),), "ocr")}
    pages = pdf.ocr(source, settings, alternatives=True, base=base)
    assert [psm for psm, _ in _psm_runs(commands)] == ["1", "11", *["6"] * strips]
    assert all(out == "stdout" for _, out in _psm_runs(commands))
    assert pages[0].words == base[1].words
    assert pages[0].text.startswith(text.strip())

    commands.clear()
    pdf.ocr(source, settings, alternatives=True)
    assert [psm for psm, _ in _psm_runs(commands)] == ["6", "1", "11", *["6"] * strips]
