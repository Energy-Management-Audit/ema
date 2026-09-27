"""Supervise one private Word process per Office operation."""

from __future__ import annotations

import atexit
import json
import shutil
import subprocess
import tempfile
import threading
import uuid
from collections.abc import Callable, Iterable, Sequence
from contextlib import suppress
from pathlib import Path
from typing import Any, ClassVar, NoReturn, cast

import psutil
from filelock import FileLock

from ema.core.office.errors import OfficeError
from ema.core.office.word import DocText, decode_word_text


def _matching_process(record: dict[str, Any], image: str) -> psutil.Process | None:
    try:
        process = psutil.Process(int(record["pid"]))
        if (
            abs(process.create_time() - float(record["create_time"])) <= 0.01
            and process.name().casefold() == image.casefold()
        ):
            return process
    except (KeyError, TypeError, ValueError, psutil.Error):
        pass
    return None


def identify_word(
    before: Iterable[int],
    started_at: float,
    word_image: str = "WINWORD.EXE",
    processes: Callable[[], Iterable[psutil.Process]] = psutil.process_iter,
) -> int | None:
    prior = set(before)
    matches: list[int] = []
    for process in processes():
        try:
            if (
                process.pid not in prior
                and process.name().casefold() == word_image.casefold()
                and process.create_time() >= started_at - 0.01
                and any(arg.casefold() == "/automation" for arg in process.cmdline())
            ):
                matches.append(process.pid)
        except (psutil.Error, OSError):
            continue
    return matches[0] if len(matches) == 1 else None


def _record(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return cast("dict[str, Any]", value) if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def _try_kill(process: psutil.Process) -> psutil.AccessDenied | None:
    try:
        process.kill()
    except psutil.NoSuchProcess:
        return None
    except psutil.AccessDenied as exc:
        return exc
    return None


class WordChild:
    _lock = threading.Lock()
    _active: ClassVar[dict[Path, tuple[subprocess.Popen[bytes], str]]] = {}

    def __init__(
        self,
        command: Sequence[str],
        timeout_s: float,
        *,
        scratch_root: Path | None = None,
        word_image: str = "WINWORD.EXE",
    ) -> None:
        self.command = list(command)
        self.timeout_s = timeout_s
        self.scratch_root = scratch_root or Path(tempfile.gettempdir()) / "ema-word"
        self.word_image = word_image

    @staticmethod
    def _launch_record(folder: Path, image: str) -> dict[str, Any] | None:
        window = _record(folder / "launch.json")
        if window is None:
            return None
        pid = identify_word(window["before"], window["started_at"], image)
        if pid is None:
            return None
        with suppress(psutil.Error):
            return {"pid": pid, "create_time": psutil.Process(pid).create_time()}
        return None

    @staticmethod
    def _kill_word(
        folder: Path,
        image: str,
        *,
        identity: dict[str, Any] | None = None,
        wait_s: float = 0,
    ) -> None:
        identity = _record(folder / "word.json") or identity
        if identity is None:
            return
        process = _matching_process(identity, image)
        if process is None:
            return
        if wait_s:
            try:
                process.wait(timeout=wait_s)
                return
            except (psutil.NoSuchProcess, psutil.ZombieProcess):
                return
            except psutil.TimeoutExpired:
                pass
        try:
            process.kill()
        except psutil.Error as exc:
            raise OfficeError("word_kill", f"Word pid {process.pid}: {exc}") from exc
        try:
            process.wait(timeout=5)
        except psutil.TimeoutExpired as exc:
            raise OfficeError("word_kill", f"Word pid {process.pid} remained after kill") from exc

    @staticmethod
    def _stop_child(child: subprocess.Popen[bytes]) -> None:
        try:
            process = psutil.Process(child.pid)
        except psutil.NoSuchProcess:
            return
        denied: psutil.AccessDenied | None = None
        try:
            descendants = process.children(recursive=True)
        except psutil.AccessDenied as exc:
            descendants = []
            denied = exc
        except psutil.NoSuchProcess:
            return
        for descendant in descendants:
            denied = _try_kill(descendant) or denied
        denied = _try_kill(process) or denied
        try:
            psutil.wait_procs([*descendants, process], timeout=5)
        except psutil.AccessDenied as exc:
            denied = exc
        if denied is not None:
            raise OfficeError("word_kill", f"Worker pid {child.pid}: {denied}") from denied

    def _sweep(self) -> None:
        for folder in self.scratch_root.iterdir():
            if not folder.is_dir() or folder in self._active:
                continue
            owner = _record(folder / "owner.json")
            if owner is not None:
                try:
                    process = psutil.Process(int(owner["pid"]))
                    if abs(process.create_time() - float(owner["create_time"])) <= 0.01:
                        continue
                except (KeyError, TypeError, ValueError, psutil.Error):
                    pass
            self._kill_word(folder, self.word_image)
            shutil.rmtree(folder, ignore_errors=True)

    @classmethod
    def on_exit(cls) -> None:
        for folder, (child, image) in tuple(cls._active.items()):
            try:
                cls._stop_child(child)
                cls._kill_word(folder, image)
            except (OSError, psutil.Error, OfficeError):
                pass

    @staticmethod
    def _tail(folder: Path) -> str:
        try:
            return (folder / "worker.log").read_text(encoding="utf-8", errors="replace")[-2000:]
        except OSError:
            return ""

    def _failed_result(self, folder: Path, result: dict[str, Any]) -> NoReturn:
        original = OfficeError(
            str(result["code"]), f"{result['detail']}; worker log: {self._tail(folder)}"
        )
        try:
            self._kill_word(folder, self.word_image, wait_s=10)
        except OfficeError as exc:
            if exc.code == "word_kill":
                raise OfficeError(
                    "word_kill", f"{exc.detail}; original {original.code}: {original.detail}"
                ) from original
            raise
        raise original

    def _result(
        self, folder: Path, action: str, source: Path, target: Path | None, exit_code: int
    ) -> DocText | None:
        result = _record(folder / "result.json")
        if result is None:
            raise OfficeError(
                "word_automation", f"worker exited {exit_code}; worker log: {self._tail(folder)}"
            )
        if not result.get("ok"):
            self._failed_result(folder, result)
        self._kill_word(folder, self.word_image, wait_s=10)
        input_name = f"in{source.suffix}"
        if action == "toc":
            source.write_bytes((folder / input_name).read_bytes())
            return None
        output_name = {"pdf": "out.pdf", "docx": "out.docx", "text": "out.txt"}.get(action)
        if output_name is None:
            return None
        output = folder / output_name
        if not output.is_file():
            raise OfficeError(
                {"pdf": "word_pdf", "docx": "word_docx", "text": "word_text"}[action],
                f"Word reported success without {output_name}",
            )
        if action == "text":
            tables = result.get("tables")
            if not isinstance(tables, int):
                raise OfficeError("word_text", "Word did not return a table count")
            return DocText(decode_word_text(output.read_bytes()), tables)
        if target is not None:
            target.write_bytes(output.read_bytes())
        return None

    def _timed_out(
        self,
        folder: Path,
        child: subprocess.Popen[bytes],
        action: str,
        cause: subprocess.TimeoutExpired,
    ) -> NoReturn:
        recorded = _record(folder / "word.json")
        launch = folder / "launch.json"
        launch_identity = (
            self._launch_record(folder, self.word_image)
            if recorded is None and launch.exists()
            else None
        )
        stop_error: OfficeError | None = None
        try:
            self._stop_child(child)
        except OfficeError as exc:
            stop_error = exc
        identity = _record(folder / "word.json") or recorded or launch_identity
        self._kill_word(folder, self.word_image, identity=identity)
        if stop_error is not None:
            raise stop_error
        detail = f"{action} exceeded {self.timeout_s} s; worker log: {self._tail(folder)}"
        if identity is None and launch.exists():
            detail += "; word process unidentified"
        raise TimeoutError(detail) from cause

    def _attempt(self, action: str, source: Path, target: Path | None) -> DocText | None:
        folder = self.scratch_root / uuid.uuid4().hex[:12]
        folder.mkdir()
        try:
            input_name = f"in{source.suffix}"
            output_name = {"pdf": "out.pdf", "docx": "out.docx", "text": "out.txt"}.get(action)
            (folder / input_name).write_bytes(source.read_bytes())
            owner = psutil.Process()
            (folder / "owner.json").write_text(
                json.dumps({"pid": owner.pid, "create_time": owner.create_time()}), encoding="utf-8"
            )
            request = folder / "request.json"
            request.write_text(
                json.dumps({"action": action, "input": input_name, "output": output_name}),
                encoding="utf-8",
            )
            with (folder / "worker.log").open("wb") as log:
                try:
                    child = subprocess.Popen(
                        [*self.command, str(request)],
                        stdin=subprocess.DEVNULL,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                except OSError as exc:
                    raise OfficeError("word_launch", str(exc)) from exc
                self._active[folder] = (child, self.word_image)
                try:
                    exit_code = child.wait(timeout=self.timeout_s)
                except subprocess.TimeoutExpired as exc:
                    self._timed_out(folder, child, action, exc)
            return self._result(folder, action, source, target, exit_code)
        finally:
            self._active.pop(folder, None)
            shutil.rmtree(folder, ignore_errors=True)

    def _perform(self, action: str, source: Path, target: Path | None = None) -> DocText | None:
        with self._lock:
            self.scratch_root.mkdir(parents=True, exist_ok=True)
            with FileLock(self.scratch_root / ".lock"):
                self._sweep()
                for attempt in range(2):
                    try:
                        return self._attempt(action, source, target)
                    except TimeoutError as exc:
                        if attempt:
                            raise OfficeError("word_timeout", str(exc)) from exc
        return None

    def update_toc_pages(self, docx: Path) -> None:
        self._perform("toc", docx)

    def render_pdf(self, docx: Path, pdf: Path) -> None:
        self._perform("pdf", docx, pdf)

    def convert_doc(self, doc: Path, out_docx: Path) -> None:
        self._perform("docx", doc, out_docx)

    def doc_text(self, doc: Path) -> DocText:
        result = self._perform("text", doc)
        if result is None:
            raise OfficeError("word_text", "Word did not return text")
        return result

    def open_check(self, docx: Path) -> None:
        self._perform("open", docx)


atexit.register(WordChild.on_exit)
