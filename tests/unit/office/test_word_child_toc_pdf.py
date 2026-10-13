"""TOC page numbers and the PDF in one supervised Word process."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from tests.unit.office.test_word_child import _child, _source

from ema.core.office import word_child as child_module
from ema.core.office.errors import OfficeError


def test_toc_and_pdf_request_and_both_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests: list[dict[str, object]] = []

    class Worker:
        pid = 456

        def __init__(self, command: list[str], **_kwargs: object) -> None:
            folder = Path(command[-1]).parent
            request = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
            requests.append(request)
            assert (folder / request["input"]).read_bytes() == b"original"
            (folder / request["input"]).write_bytes(b"page numbers set")
            (folder / request["output"]).write_bytes(b"%PDF")
            (folder / "result.json").write_text(
                json.dumps({"ok": True, "tables": None}), encoding="utf-8"
            )

        def wait(self, timeout: float) -> int:
            return 0

    monkeypatch.setattr(
        child_module,
        "subprocess",
        SimpleNamespace(
            Popen=Worker,
            DEVNULL=subprocess.DEVNULL,
            STDOUT=subprocess.STDOUT,
            TimeoutExpired=subprocess.TimeoutExpired,
        ),
    )
    word = _child(tmp_path)
    source = _source(tmp_path)
    pdf = tmp_path / "target.pdf"
    word.toc_and_pdf(source, pdf)
    assert requests == [{"action": "toc_pdf", "input": "in.docx", "output": "out.pdf"}]
    assert source.read_bytes() == b"page numbers set"
    assert pdf.read_bytes() == b"%PDF"
    assert not list(word.scratch_root.glob("*/"))


def test_toc_and_pdf_without_pdf_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMA_FAKE_WORD_MODE", "missing")
    pdf = tmp_path / "target.pdf"
    with pytest.raises(OfficeError) as error:
        _child(tmp_path).toc_and_pdf(_source(tmp_path), pdf)
    assert error.value.code == "word_pdf"
    assert not pdf.exists()


def test_toc_and_pdf_timeout_retries_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMA_FAKE_WORD_MODE", "hang_once")
    pdf = tmp_path / "target.pdf"
    _child(tmp_path, 1).toc_and_pdf(_source(tmp_path), pdf)
    assert (tmp_path / "scratch/.hang_once").is_file()
    assert pdf.read_bytes() == b"result"
