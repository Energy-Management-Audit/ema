"""Word supervision and serialization without starting Word."""

import multiprocessing
import re
import subprocess
import threading
import time
from pathlib import Path

import pytest

from ema.core.errors import EmaError
from ema.core.office.errors import OfficeError
from ema.core.office.word import OsaResult, WordMac


def adapter(tmp_path, runner):
    app = tmp_path / "Word.app"
    app.mkdir()
    word = WordMac(app=app, timeout_s=2, runner=runner)
    word.work_root = tmp_path / "copies"
    word._restart = lambda: None
    word._force_quit = lambda: None
    source = tmp_path / "source.docx"
    source.write_bytes(b"synthetic")
    return word, source


def copies(word):
    return [path for path in word.work_root.iterdir() if path.name != ".word.lock"]


def test_permission_error_cleans_copy(tmp_path):
    word, source = adapter(tmp_path, lambda _script, _timeout: OsaResult(1, "", "error -1743"))
    with pytest.raises(OfficeError) as error:
        word.open_check(source)
    assert error.value.code == "word_permission"
    assert "Automatizare" in error.value.user_message_ro
    assert copies(word) == []


def test_launch_failure_cleans_copy_and_exposes_safe_error(tmp_path):
    def runner(_script, _timeout):
        assert copies(word)
        raise OSError("osascript unavailable")

    word, source = adapter(tmp_path, runner)
    with pytest.raises(EmaError) as error:
        word.open_check(source)
    assert error.value.code == "word_launch"
    assert error.value.user_message_ro == "Automatizarea Microsoft Word nu a putut fi pornită."
    assert "osascript unavailable" in error.value.detail
    assert isinstance(error.value.__cause__, OSError)
    assert copies(word) == []


def test_unexpected_runner_error_closes_possible_word_copy(tmp_path):
    calls = []

    def runner(script, _timeout):
        calls.append(script)
        if len(calls) == 1:
            raise RuntimeError("runner failed after launch")
        assert "close document" in script
        assert copies(word)
        return OsaResult(0, "", "")

    word, source = adapter(tmp_path, runner)
    with pytest.raises(OfficeError) as error:
        word.open_check(source)
    assert error.value.code == "word_automation"
    assert isinstance(error.value.__cause__, RuntimeError)
    assert len(calls) == 2
    assert copies(word) == []


def test_unexpected_close_error_force_quits_before_removing_copy(tmp_path):
    calls = []

    def runner(_script, _timeout):
        calls.append(True)
        raise RuntimeError("runner stopped")

    word, source = adapter(tmp_path, runner)
    quits = []
    word._force_quit = lambda: quits.append(bool(copies(word)))
    with pytest.raises(OfficeError) as error:
        word.open_check(source)
    assert error.value.code == "word_automation"
    assert calls == [True, True]
    assert quits == [True]
    assert copies(word) == []


@pytest.mark.parametrize(
    "code",
    [
        "word_permission",
        "word_missing",
        "word_timeout",
        "word_automation",
        "word_restart",
        "word_launch",
        "word_pdf",
        "chart_formula",
        "chart_cache",
        "chart_location",
        "chart_series",
        "chart_title",
        "chart_style",
    ],
)
def test_office_errors_have_romanian_user_messages(code):
    error = OfficeError(code, "private detail")
    assert isinstance(error, EmaError)
    assert error.user_message_ro
    assert error.detail == "private detail"
    assert "private detail" not in error.user_message_ro


def test_timeout_restarts_then_retries(tmp_path):
    calls = []

    def runner(script, _timeout):
        calls.append(script)
        if len(calls) == 1:
            raise TimeoutError("hung")
        return OsaResult(0, "", "")

    word, source = adapter(tmp_path, runner)
    restarts = []
    quits = []
    word._force_quit = lambda: quits.append(bool(copies(word)))
    word._restart = lambda: restarts.append(copies(word) == [])
    word.open_check(source)
    assert quits == [True]
    assert restarts == [True]
    assert len(calls) == 2
    assert calls[0] != calls[1]
    assert copies(word) == []


def test_two_timeouts_raise_and_clean(tmp_path):
    word, source = adapter(
        tmp_path, lambda _script, _timeout: (_ for _ in ()).throw(TimeoutError())
    )
    restarts = []
    quits = []
    word._force_quit = lambda: quits.append(bool(copies(word)))
    word._restart = lambda: restarts.append(True)
    with pytest.raises(OfficeError) as error:
        word.open_check(source)
    assert error.value.code == "word_timeout"
    assert len(restarts) == 1
    assert quits == [True, True]
    assert copies(word) == []


def test_process_timeout_keeps_stderr(tmp_path):
    def runner(_script, _timeout):
        raise subprocess.TimeoutExpired("osascript", 2, stderr=b"word stalled")

    word, source = adapter(tmp_path, runner)
    with pytest.raises(OfficeError) as error:
        word.open_check(source)
    assert error.value.code == "word_timeout"
    assert "word stalled" in error.value.detail


def test_failed_open_closes_before_copy_cleanup(tmp_path):
    calls = []

    def runner(script, _timeout):
        calls.append(script)
        if len(calls) == 1:
            return OsaResult(1, "", "Word action failed")
        assert copies(word)
        assert "close document" in script
        return OsaResult(0, "", "")

    word, source = adapter(tmp_path, runner)
    with pytest.raises(OfficeError) as error:
        word.open_check(source)
    assert error.value.code == "word_automation"
    assert len(calls) == 2
    assert copies(word) == []


def test_failed_cleanup_force_quits_before_removing_copy(tmp_path):
    calls = []

    def runner(_script, _timeout):
        calls.append(True)
        return OsaResult(1, "", "failed")

    word, source = adapter(tmp_path, runner)
    quits = []
    word._force_quit = lambda: quits.append(bool(copies(word)))
    with pytest.raises(OfficeError) as error:
        word.open_check(source)
    assert len(calls) == 2
    assert quits == [True]
    assert "cleanup forced Word quit" in error.value.detail
    assert copies(word) == []


def _word_child(app, source, work_root, active, maximum):
    def runner(_script, _timeout):
        with active.get_lock():
            active.value += 1
            maximum.value = max(maximum.value, active.value)
        time.sleep(0.1)
        with active.get_lock():
            active.value -= 1
        return OsaResult(0, "", "")

    word = WordMac(app=app, timeout_s=2, runner=runner)
    word.work_root = work_root
    word.open_check(source)


def test_processes_are_serialized(tmp_path):
    context = multiprocessing.get_context("fork")
    app = tmp_path / "Word.app"
    app.mkdir()
    source = tmp_path / "source.docx"
    source.write_bytes(b"synthetic")
    active, maximum = context.Value("i", 0), context.Value("i", 0)
    args = (app, source, tmp_path / "copies", active, maximum)
    processes = [context.Process(target=_word_child, args=args) for _ in range(2)]
    for process in processes:
        process.start()
    for process in processes:
        process.join(5)
        assert process.exitcode == 0
    assert maximum.value == 1


def test_failed_force_quit_keeps_primary_error_and_removes_copy(tmp_path, monkeypatch):
    word, source = adapter(
        tmp_path, lambda _script, _timeout: (_ for _ in ()).throw(TimeoutError("hung"))
    )
    word._force_quit = WordMac._force_quit.__get__(word)
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command[0])
        return subprocess.CompletedProcess(
            command, 1 if "killall" in command[0] else 0, "Word still running", "kill failed"
        )

    monkeypatch.setattr("ema.core.office.word.subprocess.run", fake_run)
    monkeypatch.setattr("ema.core.office.word.time.monotonic", iter([0, 3]).__next__)
    with pytest.raises(OfficeError) as error:
        word.open_check(source)
    assert error.value.code == "word_restart"
    assert "hung" in error.value.detail and "kill failed" in error.value.detail
    assert calls == ["/usr/bin/killall", "/usr/bin/pgrep"]
    assert copies(word) == []


def test_threads_are_serialized(tmp_path):
    active = 0
    maximum = 0
    lock = threading.Lock()

    def runner(_script, _timeout):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.01)
        with lock:
            active -= 1
        return OsaResult(0, "", "")

    word, source = adapter(tmp_path, runner)
    threads = [threading.Thread(target=word.open_check, args=(source,)) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert maximum == 1


def test_doc_actions_copy_results_and_count_tables(tmp_path):
    scripts = []

    def runner(script, _timeout):
        scripts.append(script)
        match = re.search(r'save as d file name "([^"]+)" file format', script)
        assert match is not None
        output = Path(match.group(1))
        output.write_bytes(b"converted" if output.suffix == ".docx" else b"alpha beta")
        return OsaResult(0, "2" if output.suffix == ".txt" else "", "")

    word, source = adapter(tmp_path, runner)
    source = source.with_suffix(".doc")
    source.write_bytes(b"legacy")
    target = tmp_path / "converted.docx"
    word.convert_doc(source, target)
    extracted = word.doc_text(source)
    assert target.read_bytes() == b"converted"
    assert extracted.text == "alpha beta"
    assert extracted.tables == 2
    assert "file format format document" in scripts[0]
    assert "set d to save as d" not in scripts[0]
    assert re.search(
        r'file format format document\nset d to document "[0-9a-f]{32}\.docx"\nclose d saving no',
        scripts[0],
    )
    assert "count of tables of d" in scripts[1]
    assert "file format format text" in scripts[1]
    assert "set d to save as d" not in scripts[1]
    assert re.search(
        r'file format format text\nset d to document "[0-9a-f]{32}\.txt"\nclose d saving no',
        scripts[1],
    )
    assert "set d to active document" not in scripts[0] + scripts[1]
    assert re.search(r"/[0-9a-f]{32}\.docx", scripts[0])
    assert re.search(r"/[0-9a-f]{32}\.txt", scripts[1])
    assert copies(word) == []


def test_failed_save_as_cleanup_addresses_old_and_new_names(tmp_path):
    scripts = []

    def runner(script, _timeout):
        scripts.append(script)
        if len(scripts) == 1:
            return OsaResult(1, "", "save failed")
        return OsaResult(0, "", "")

    word, source = adapter(tmp_path, runner)
    target = tmp_path / "converted.docx"
    with pytest.raises(OfficeError):
        word.convert_doc(source, target)
    match = re.search(r'file name "([^"]+\.docx)"', scripts[0])
    assert match is not None
    assert f'if exists document "{Path(match.group(1)).name}"' in scripts[1]
    assert source.name in scripts[1]
    assert copies(word) == []


def test_unknown_office_code_keeps_generic_message():
    error = OfficeError("unlisted", "private detail")
    assert error.user_message_ro == "Operația Office a eșuat."
    assert error.detail == "private detail"
