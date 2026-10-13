"""TOC page numbers and the PDF in one Word for Mac open, without starting Word."""

import re
from pathlib import Path

import pytest
from tests.unit.office.test_word import adapter, copies

from ema.core.office.errors import OfficeError
from ema.core.office.word import OsaResult


def _pdf_runner(scripts, *, write_pdf=True):
    def runner(script, _timeout):
        scripts.append(script)
        copy = Path(re.search(r'open \(POSIX file "([^"]+)"\)', script).group(1))
        copy.write_bytes(b"page numbers set")
        if write_pdf:
            Path(re.search(r'save as d file name "([^"]+)"', script).group(1)).write_bytes(b"%PDF")
        return OsaResult(0, "", "")

    return runner


def test_toc_and_pdf_is_one_open_with_both_files_copied_back(tmp_path):
    scripts = []
    word, source = adapter(tmp_path, _pdf_runner(scripts))
    pdf = tmp_path / "out.pdf"
    word.toc_and_pdf(source, pdf)
    assert len(scripts) == 1
    commands = scripts[0].splitlines()[2:-2]
    assert [re.sub(r'"[^"]+"', '""', command) for command in commands] == [
        'open (POSIX file "")',
        'set d to document ""',
        "update page numbers of table of contents 1 of d",
        "save d",
        'save as d file name "" file format format PDF',
        "close d saving no",
    ]
    assert re.search(r'[/\\]converted\.pdf" file format format PDF', scripts[0])
    assert source.read_bytes() == b"page numbers set"
    assert pdf.read_bytes() == b"%PDF"
    assert copies(word) == []


def test_toc_and_pdf_without_pdf_is_an_error(tmp_path):
    word, source = adapter(tmp_path, _pdf_runner([], write_pdf=False))
    pdf = tmp_path / "out.pdf"
    with pytest.raises(OfficeError) as error:
        word.toc_and_pdf(source, pdf)
    assert error.value.code == "word_pdf"
    assert not pdf.exists()
    assert source.read_bytes() == b"page numbers set"
    assert copies(word) == []


def test_toc_and_pdf_timeout_restarts_then_retries(tmp_path):
    scripts = []
    succeed = _pdf_runner(scripts)

    def runner(script, timeout):
        if not scripts:
            scripts.append(script)
            raise TimeoutError("hung")
        return succeed(script, timeout)

    word, source = adapter(tmp_path, runner)
    restarts = []
    quits = []
    word._force_quit = lambda: quits.append(bool(copies(word)))
    word._restart = lambda: restarts.append(copies(word) == [])
    pdf = tmp_path / "out.pdf"
    word.toc_and_pdf(source, pdf)
    assert (quits, restarts, len(scripts)) == ([True], [True], 2)
    assert source.read_bytes() == b"page numbers set"
    assert pdf.read_bytes() == b"%PDF"
    assert copies(word) == []


def test_toc_and_pdf_permission_error_leaves_files_alone(tmp_path):
    word, source = adapter(tmp_path, lambda _script, _timeout: OsaResult(1, "", "error -1743"))
    pdf = tmp_path / "out.pdf"
    with pytest.raises(OfficeError) as error:
        word.toc_and_pdf(source, pdf)
    assert error.value.code == "word_permission"
    assert source.read_bytes() == b"synthetic"
    assert not pdf.exists()
    assert copies(word) == []


def test_toc_and_pdf_failed_open_closes_before_copy_cleanup(tmp_path):
    scripts = []

    def runner(script, _timeout):
        scripts.append(script)
        if len(scripts) == 1:
            return OsaResult(1, "", "Word action failed")
        assert copies(word)
        return OsaResult(0, "", "")

    word, source = adapter(tmp_path, runner)
    with pytest.raises(OfficeError) as error:
        word.toc_and_pdf(source, tmp_path / "out.pdf")
    assert error.value.code == "word_automation"
    assert len(scripts) == 2
    assert 'if exists document "converted.pdf" then close document "converted.pdf"' in scripts[1]
    assert f'-{source.name}" then close document' in scripts[1]
    assert source.read_bytes() == b"synthetic"
    assert copies(word) == []


def test_toc_and_pdf_has_twice_the_budget_and_pdf_keeps_one(tmp_path):
    seen = []

    def runner(script, timeout):
        seen.append((script.splitlines()[0], timeout))
        copy = Path(re.search(r'open \(POSIX file "([^"]+)"\)', script).group(1))
        copy.write_bytes(b"x")
        Path(re.search(r'save as d file name "([^"]+)"', script).group(1)).write_bytes(b"%PDF")
        return OsaResult(0, "", "")

    word, source = adapter(tmp_path, runner)
    word.toc_and_pdf(source, tmp_path / "a.pdf")
    word.render_pdf(source, tmp_path / "b.pdf")
    assert seen == [("with timeout of 4 seconds", 9), ("with timeout of 2 seconds", 7)]
