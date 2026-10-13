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
from ema.invoices.reader import InvoiceDocumentReader


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


class _Runs:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.cwds: list[object] = []
        self.inputs: list[bytes] = []


def _fake_run(
    monkeypatch: pytest.MonkeyPatch,
    text: str = "page text\n",
    tsv: str = "tsv rows\n",
    write: tuple[str, ...] = (".txt", ".tsv"),
    stderr: bytes = b"",
) -> _Runs:
    runs = _Runs()

    def run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        runs.commands.append(args)
        runs.cwds.append(kwargs.get("cwd"))
        runs.inputs.append(kwargs["input"])
        if args[2] != "stdout":
            folder = Path(kwargs["cwd"])
            contents = {".txt": text, ".tsv": tsv}
            for suffix in write:
                (folder / (args[2] + suffix)).write_bytes(contents[suffix].encode())
        return subprocess.CompletedProcess(args, 0, b"", stderr)

    monkeypatch.setattr(pdf.subprocess, "run", run)
    return runs


def test_page_run_is_one_invocation_with_both_renderers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs = _fake_run(monkeypatch)
    commands = runs.commands
    monkeypatch.setattr(pdf, "resource_path", tmp_path.joinpath)
    bundled = tmp_path / "tesseract" / "tesseract.exe"

    assert pdf._run_tesseract_page(bundled, b"image", "ron", 2) == ("page text\n", "tsv rows\n")
    assert len(commands) == 1
    command = commands[0]
    assert command[0] == str(bundled)
    assert command[1] == "stdin"
    assert command[2] == "page"
    assert command[3:5] == ["--tessdata-dir", str(tmp_path / "tesseract" / "tessdata")]
    assert command[5:] == ["--dpi", "200", "-l", "ron", "--psm", "6", "txt", "tsv"]
    # The files are read from the directory Tesseract ran in, and no path is an argument.
    folder = runs.cwds[0]
    assert isinstance(folder, Path)
    assert not any(str(folder) in argument for argument in command)

    pdf._run_tesseract_page(Path("/opt/homebrew/bin/tesseract"), b"image", "ron", 2)
    assert "--tessdata-dir" not in commands[1]
    assert commands[1][:3] == [str(Path("/opt/homebrew/bin/tesseract")), "stdin", "page"]


def test_page_run_without_output_files_is_ocr_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = Path("/opt/homebrew/bin/tesseract")
    _fake_run(monkeypatch, write=(), stderr=b"Error opening data file")
    with pytest.raises(EmaError) as nothing:
        pdf._run_tesseract_page(executable, b"image", "ron", 2)
    assert nothing.value.code == "ocr_failed"
    assert nothing.value.detail == "Error opening data file"

    _fake_run(monkeypatch, write=(), stderr=b"e" * 1500)
    with pytest.raises(EmaError) as long:
        pdf._run_tesseract_page(executable, b"image", "ron", 2)
    assert long.value.detail == "e" * 1000

    _fake_run(monkeypatch, write=(), stderr=b"")
    with pytest.raises(EmaError) as silent:
        pdf._run_tesseract_page(executable, b"image", "ron", 2)
    assert silent.value.code == "ocr_failed"
    assert silent.value.detail

    for present in ((".txt",), (".tsv",)):
        _fake_run(monkeypatch, write=present, stderr=b"one file only")
        with pytest.raises(EmaError) as partial:
            pdf._run_tesseract_page(executable, b"image", "ron", 2)
        assert partial.value.code == "ocr_failed"
        assert partial.value.detail == "one file only"


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
    # Tesseract's text-mode stdout is CRLF on Windows; the files are LF everywhere.
    expected = (expected[0].replace("\r\n", "\n"), expected[1].replace("\r\n", "\n"))
    assert pdf._run_tesseract_page(executable, png, "ron+eng", 120) == expected


def _scan(tmp_path: Path) -> Path:
    return _pdf(tmp_path / "scan.pdf")


def _psm_runs(runs: _Runs) -> list[tuple[str, str]]:
    return [(c[c.index("--psm") + 1], c[2]) for c in runs.commands]


def _full_page_png(source: Path) -> bytes:
    with pypdfium2.PdfDocument(source) as document:
        page: Any = document[0]
        buffer = io.BytesIO()
        page.render(scale=200 / 72).to_pil().save(buffer, format="PNG", compress_level=1)
    return buffer.getvalue()


@pytest.mark.parametrize("text", ["plain\n", "Factura 1\n"])
def test_ocr_run_counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    runs = _fake_run(monkeypatch, text=text)
    settings = Settings(tesseract_path=tmp_path / "tesseract")
    settings.tesseract_path.write_bytes(b"")
    source = _scan(tmp_path)
    strips = 3 if "factur" in text.casefold() else 0
    full_page = _full_page_png(source)

    pdf.ocr(source, settings)
    assert [psm for psm, _ in _psm_runs(runs)] == ["6"]
    assert runs.inputs == [full_page]

    runs.commands.clear()
    runs.inputs.clear()
    base = {1: pdf.PageText(1, text, (pdf.Word("w", 1, 2, 3, 4),), "ocr")}
    pages = pdf.ocr(source, settings, alternatives=True, base=base)
    assert [psm for psm, _ in _psm_runs(runs)] == ["1", "11", *["6"] * strips]
    assert all(out == "stdout" for _, out in _psm_runs(runs))
    assert runs.inputs[:2] == [full_page, full_page]
    assert pages[0].words == base[1].words
    assert pages[0].text.startswith(text.strip())

    runs.commands.clear()
    pdf.ocr(source, settings, alternatives=True)
    assert [psm for psm, _ in _psm_runs(runs)] == ["6", "1", "11", *["6"] * strips]


def test_base_covering_some_pages_runs_psm_6_for_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs = _fake_run(monkeypatch)
    settings = Settings(tesseract_path=tmp_path / "tesseract")
    settings.tesseract_path.write_bytes(b"")
    source = _scan(tmp_path)

    pdf.ocr(source, settings, base={2: pdf.PageText(2, "other\n", (), "ocr")})
    assert [psm for psm, _ in _psm_runs(runs)] == ["6"]


def test_reader_reuses_first_pass_as_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs = _fake_run(monkeypatch, text="Alive Capital\n")
    settings = Settings(tesseract_path=tmp_path / "tesseract")
    settings.tesseract_path.write_bytes(b"")

    InvoiceDocumentReader(settings).read(_scan(tmp_path))
    assert [psm for psm, _ in _psm_runs(runs)] == ["6", "1", "11"]
