"""The Word supervisor kills only the process it can identify."""

import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import psutil
import pytest

from ema.core.office import word_child as child_module
from ema.core.office.errors import OfficeError
from ema.core.office.word_child import WordChild

FAKE = Path(__file__).parents[2] / "fixtures/office/fake_word_worker.py"


def _child(tmp_path: Path, timeout: float = 1) -> WordChild:
    probe = _bystander()
    image = psutil.Process(probe.pid).name()
    probe.kill()
    probe.wait()
    return WordChild(
        [sys.executable, str(FAKE)],
        timeout,
        scratch_root=tmp_path / "scratch",
        word_image=image,
    )


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "input.docx"
    source.write_bytes(b"original")
    return source


def _bystander(executable: str | None = None) -> subprocess.Popen[bytes]:
    process = subprocess.Popen(
        [
            executable or sys.executable,
            "-c",
            "import sys,time; sys.stdout.buffer.write(b'ready\\n'); "
            "sys.stdout.buffer.flush(); time.sleep(60)",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    assert process.stdout is not None
    assert process.stdout.readline() == b"ready\n"
    return process


def test_each_action_and_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMA_FAKE_WORD_MODE", "ok")
    word = _child(tmp_path)
    source = _source(tmp_path)
    word.update_toc_pages(source)
    assert source.read_bytes() == b"updated toc"
    pdf = tmp_path / "out.pdf"
    word.render_pdf(source, pdf)
    assert pdf.read_bytes() == b"result"
    docx = tmp_path / "out.docx"
    word.convert_doc(source, docx)
    assert docx.read_bytes() == b"result"
    text = word.doc_text(source)
    assert (text.text, text.tables) == ("text with accent", 2)
    word.open_check(source)
    assert not list(word.scratch_root.glob("*/request.json"))


def test_failed_source_copy_cleans_attempt_folder(tmp_path: Path) -> None:
    word = _child(tmp_path)
    with pytest.raises(FileNotFoundError):
        word.open_check(tmp_path / "missing.docx")
    assert not list(word.scratch_root.glob("*/"))


@pytest.mark.parametrize("mode,code", [("crash", "word_automation"), ("fail", "word_launch")])
def test_worker_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, code: str
) -> None:
    monkeypatch.setenv("EMA_FAKE_WORD_MODE", mode)
    with pytest.raises(OfficeError) as error:
        _child(tmp_path).open_check(_source(tmp_path))
    assert error.value.code == code
    assert (
        "fake crash marker" in error.value.detail
        if mode == "crash"
        else "fake failure" in error.value.detail
    )


def test_timeout_kills_word_and_spares_bystander(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMA_FAKE_WORD_MODE", "hang")
    bystander = _bystander()
    identity = psutil.Process(bystander.pid).create_time()
    try:
        with pytest.raises(OfficeError) as error:
            _child(tmp_path, 1).open_check(_source(tmp_path))
        assert error.value.code == "word_timeout"
        assert psutil.Process(bystander.pid).create_time() == identity
        assert bystander.poll() is None
        pids = [
            int(value)
            for value in (tmp_path / "scratch/.word_pids").read_text(encoding="utf-8").splitlines()
        ]
        assert len(pids) == 2
        assert all(
            not psutil.pid_exists(pid) or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
            for pid in pids
        )
    finally:
        bystander.kill()
        bystander.wait()


def test_timeout_retries_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMA_FAKE_WORD_MODE", "hang_once")
    _child(tmp_path, 1).open_check(_source(tmp_path))
    assert (tmp_path / "scratch/.hang_once").is_file()


@pytest.mark.parametrize(
    "action,code", [("pdf", "word_pdf"), ("docx", "word_docx"), ("text", "word_text")]
)
def test_success_without_output_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str, code: str
) -> None:
    monkeypatch.setenv("EMA_FAKE_WORD_MODE", "missing")
    word = _child(tmp_path)
    source = _source(tmp_path)
    with pytest.raises(OfficeError) as error:
        if action == "pdf":
            word.render_pdf(source, tmp_path / "out.pdf")
        elif action == "docx":
            word.convert_doc(source, tmp_path / "out.docx")
        else:
            word.doc_text(source)
    assert error.value.code == code


@pytest.mark.parametrize("mode,unidentified", [("hang_launch", False), ("hang_launch_two", True)])
def test_launch_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, unidentified: bool
) -> None:
    monkeypatch.setenv("EMA_FAKE_WORD_MODE", mode)
    word = _child(tmp_path, 1)
    bystander: subprocess.Popen[bytes] | None = None
    pids: list[int] = []
    private_pids: list[int] = []

    # The scanner predicate has its own tests; this isolates the supervisor from runner processes.
    monkeypatch.setattr(
        child_module,
        "identify_word",
        lambda *_args: private_pids[0] if len(private_pids) == 1 else None,
    )

    class ReadyPopen(subprocess.Popen[bytes]):
        def wait(self, timeout: float | None = None) -> int:
            nonlocal bystander
            ready = Path(str(self.args[-1])).parent / "ready"
            deadline = time.monotonic() + 30
            while not ready.is_file():
                if self.poll() is not None:
                    raise AssertionError("fake worker exited before launch readiness")
                if time.monotonic() >= deadline:
                    raise AssertionError("fake worker never signalled launch readiness")
                time.sleep(0.01)
            private_pids[:] = [
                json.loads(path.read_text(encoding="utf-8"))["pid"]
                for path in ready.parent.glob("dummy*.json")
            ]
            private_word = psutil.Process(private_pids[0])
            word.word_image = private_word.name()
            if bystander is None:
                bystander = _bystander(private_word.cmdline()[0])
                assert psutil.Process(bystander.pid).name() == word.word_image
            raise subprocess.TimeoutExpired(self.args, timeout)

    monkeypatch.setattr(
        child_module,
        "subprocess",
        SimpleNamespace(
            Popen=ReadyPopen,
            DEVNULL=subprocess.DEVNULL,
            STDOUT=subprocess.STDOUT,
            TimeoutExpired=subprocess.TimeoutExpired,
        ),
    )
    word.scratch_root.mkdir()
    try:
        with pytest.raises(TimeoutError) as error:
            word._attempt("open", _source(tmp_path), None)
        assert ("word process unidentified" in str(error.value)) == unidentified
        assert bystander is not None and bystander.poll() is None
        pids = [
            int(value)
            for value in (tmp_path / "scratch/.word_pids").read_text(encoding="utf-8").splitlines()
        ]
        assert len(pids) == (2 if unidentified else 1)
        assert (
            all(psutil.pid_exists(pid) for pid in pids)
            if unidentified
            else all(
                not psutil.pid_exists(pid) or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
                for pid in pids
            )
        )
    finally:
        if bystander is not None:
            bystander.kill()
            bystander.wait()
        for pid in pids:
            try:
                process = psutil.Process(pid)
                if process.name() == word.word_image and "/Automation" in process.cmdline():
                    process.kill()
            except psutil.Error:
                pass


@pytest.mark.parametrize("stop_fails", [False, True])
def test_timeout_scans_before_stopping_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stop_fails: bool
) -> None:
    word = _child(tmp_path)
    word.scratch_root.mkdir()
    source = _source(tmp_path)
    events: list[object] = []
    identity = {"pid": 123, "create_time": 42.0}

    class TimedOutChild:
        pid = 456

        def __init__(self, command: list[str], **_kwargs: object) -> None:
            (Path(command[-1]).parent / "launch.json").write_text("{}", encoding="utf-8")

        def wait(self, timeout: float) -> int:
            raise subprocess.TimeoutExpired("fake", timeout)

    monkeypatch.setattr(
        child_module,
        "subprocess",
        SimpleNamespace(
            Popen=TimedOutChild,
            DEVNULL=subprocess.DEVNULL,
            STDOUT=subprocess.STDOUT,
            TimeoutExpired=subprocess.TimeoutExpired,
        ),
    )
    monkeypatch.setattr(
        WordChild,
        "_launch_record",
        staticmethod(lambda _folder, _image: (events.append("scan"), identity)[1]),
    )

    def stop(_child: object) -> None:
        events.append("child")
        if stop_fails:
            raise OfficeError("word_kill", "worker inaccessible")

    monkeypatch.setattr(WordChild, "_stop_child", staticmethod(stop))
    monkeypatch.setattr(
        WordChild,
        "_kill_word",
        staticmethod(lambda _folder, _image, **kwargs: events.append(("word", kwargs["identity"]))),
    )
    with pytest.raises(OfficeError if stop_fails else TimeoutError):
        word._attempt("open", source, None)
    assert events == ["scan", "child", ("word", identity), ("word", None)]


@pytest.mark.parametrize("failure", ["vanished", "denied"])
def test_stop_child_kills_child_after_descendant_failure(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    events: list[str] = []

    class Descendant:
        def kill(self) -> None:
            events.append("descendant")
            if failure == "vanished":
                raise psutil.NoSuchProcess(321)
            raise psutil.AccessDenied(321)

    class Process:
        def children(self, *, recursive: bool) -> list[Descendant]:
            assert recursive
            return [Descendant()]

        def kill(self) -> None:
            events.append("child")

    monkeypatch.setattr(child_module.psutil, "Process", lambda _pid: Process())
    monkeypatch.setattr(child_module.psutil, "wait_procs", lambda *_args, **_kwargs: None)
    child = SimpleNamespace(pid=456)
    if failure == "denied":
        with pytest.raises(OfficeError) as error:
            WordChild._stop_child(child)
        assert error.value.code == "word_kill"
        assert "Worker pid 456" in error.value.detail
    else:
        WordChild._stop_child(child)
    assert events == ["descendant", "child"]


def test_word_kill_preserves_worker_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    word = _child(tmp_path)
    (tmp_path / "result.json").write_text(
        json.dumps({"ok": False, "code": "word_automation", "detail": "COM detail"}),
        encoding="utf-8",
    )
    (tmp_path / "worker.log").write_text("worker trace", encoding="utf-8")

    def stuck(*_args: object, **_kwargs: object) -> None:
        raise OfficeError("word_kill", "private Word remained")

    monkeypatch.setattr(word, "_kill_word", stuck)
    with pytest.raises(OfficeError) as error:
        word._result(tmp_path, "open", tmp_path / "in.docx", None, 1)
    assert error.value.code == "word_kill"
    assert "private Word remained" in error.value.detail
    assert "original word_automation: COM detail; worker log: worker trace" in error.value.detail
    assert isinstance(error.value.__cause__, OfficeError)
    assert error.value.__cause__.code == "word_automation"


def test_sweep_dead_owner_and_live_owner(tmp_path: Path) -> None:
    word = _child(tmp_path)
    word.scratch_root.mkdir()
    owner = psutil.Process()
    live = word.scratch_root / "live"
    live.mkdir()
    (live / "owner.json").write_text(
        json.dumps({"pid": owner.pid, "create_time": owner.create_time()}), encoding="utf-8"
    )
    live_word = _bystander()
    (live / "word.json").write_text(
        json.dumps(
            {"pid": live_word.pid, "create_time": psutil.Process(live_word.pid).create_time()}
        ),
        encoding="utf-8",
    )
    stale = word.scratch_root / "stale"
    stale.mkdir()
    (stale / "owner.json").write_text(
        json.dumps({"pid": owner.pid, "create_time": 0}), encoding="utf-8"
    )
    dummy = _bystander()
    identity = psutil.Process(dummy.pid)
    (stale / "word.json").write_text(
        json.dumps({"pid": dummy.pid, "create_time": identity.create_time()}), encoding="utf-8"
    )
    try:
        word._sweep()
        assert live.exists() and not stale.exists()
        assert live_word.poll() is None
        dummy.wait(timeout=5)
    finally:
        live_word.kill()
        live_word.wait()
        if dummy.poll() is None:
            dummy.kill()
            dummy.wait()


def test_exit_hook_stops_in_flight_child(tmp_path: Path) -> None:
    word = _child(tmp_path)
    word.scratch_root.mkdir()
    folder = word.scratch_root / "in-flight"
    folder.mkdir()
    child = _bystander()
    private_word = _bystander()
    (folder / "word.json").write_text(
        json.dumps(
            {"pid": private_word.pid, "create_time": psutil.Process(private_word.pid).create_time()}
        ),
        encoding="utf-8",
    )
    WordChild._active[folder] = (child, word.word_image)
    WordChild.on_exit()
    child.wait(timeout=5)
    private_word.wait(timeout=5)
    assert child.returncode is not None
    assert private_word.returncode is not None
    WordChild._active.pop(folder)
