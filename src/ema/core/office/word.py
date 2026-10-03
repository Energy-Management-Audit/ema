"""Supervised Word for Mac operations on isolated document copies."""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol

from filelock import FileLock

from ema.core.office.errors import OfficeError


@dataclass(frozen=True)
class OsaResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class DocText:
    text: str
    tables: int


def decode_word_text(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("utf-16")


class OsaRunner(Protocol):
    def __call__(self, script: str, timeout_s: float) -> OsaResult: ...


def _run_osa(script: str, timeout_s: float) -> OsaResult:
    result = subprocess.run(
        ["/usr/bin/osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    return OsaResult(result.returncode, result.stdout, result.stderr)


def _apple_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class WordMac:
    _lock = threading.Lock()
    _session_lock = threading.RLock()
    _session_depth = 0

    def __init__(
        self,
        app: Path = Path("/Applications/Microsoft Word.app"),
        timeout_s: float = 120,
        runner: OsaRunner | None = None,
        process_probe: Callable[[], bool] | None = None,
    ) -> None:
        self.app = app
        self.timeout_s = timeout_s
        self.runner = runner or _run_osa
        self.process_probe = process_probe or self.word_running
        self.work_root = Path.home() / "Library/Containers/com.microsoft.Word/Data/Ema"

    @contextmanager
    def _process_lock(self):
        self.work_root.mkdir(parents=True, exist_ok=True)
        with FileLock(self.work_root / ".word.lock"):
            yield

    @staticmethod
    def word_running() -> bool:
        probe = subprocess.run(
            ["/usr/bin/pgrep", "-x", "Microsoft Word"],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode not in (0, 1):
            raise OfficeError("word_automation", f"Word process probe failed: {probe.stderr}")
        return probe.returncode == 0

    def quit_if_idle(self) -> None:
        result = self.runner(
            'tell application "Microsoft Word" to count of documents', self.timeout_s + 5
        )
        if result.returncode:
            raise OfficeError("word_automation", result.stderr or result.stdout)
        try:
            count = int(result.stdout.strip())
        except ValueError as exc:
            raise OfficeError(
                "word_automation", f"Invalid Word document count: {result.stdout!r}"
            ) from exc
        if count:
            return
        result = self.runner(
            'tell application "Microsoft Word" to quit saving no', self.timeout_s + 5
        )
        deadline = time.monotonic() + 10
        while self.process_probe():
            if time.monotonic() >= deadline:
                self._force_quit()
                return
            time.sleep(0.1)
        if result.returncode:
            raise OfficeError("word_automation", result.stderr or result.stdout)

    @contextmanager
    def word_session(self):
        with self._session_lock:
            outermost = WordMac._session_depth == 0
            was_running = self.process_probe() if outermost else True
            WordMac._session_depth += 1
            try:
                yield self
            finally:
                WordMac._session_depth -= 1
                if outermost and not was_running and self.process_probe():
                    self.quit_if_idle()

    def _force_quit(self) -> None:
        kill = subprocess.run(
            ["/usr/bin/killall", "-9", "Microsoft Word"],
            capture_output=True,
            text=True,
            check=False,
        )
        deadline = time.monotonic() + 2
        while True:
            probe = subprocess.run(
                ["/usr/bin/pgrep", "-x", "Microsoft Word"],
                capture_output=True,
                text=True,
                check=False,
            )
            if probe.returncode == 1:
                return
            if time.monotonic() >= deadline:
                raise OfficeError(
                    "word_restart",
                    "Word remains open after force quit "
                    f"(killall: {kill.stderr or kill.returncode}; "
                    f"pgrep: {probe.stderr or probe.stdout or probe.returncode})",
                )
            time.sleep(0.05)

    def _restart(self) -> None:
        subprocess.run(
            ["/usr/bin/open", "-a", str(self.app)],
            capture_output=True,
            text=True,
            timeout=self.timeout_s,
            check=True,
        )

    def _script(self, action: str, document: Path, output: Path | None = None) -> str:
        path = _apple_string(str(document))
        name = _apple_string(document.name)
        commands = [
            f"open (POSIX file {path})",
            f"set d to document {name}",
        ]
        if action == "toc":
            commands.extend(["update page numbers of table of contents 1 of d", "save d"])
        elif action == "pdf" and output is not None:
            commands.append(
                f"save as d file name {_apple_string(str(output))} file format format PDF"
            )
        elif action == "docx" and output is not None:
            commands.append(
                f"save as d file name {_apple_string(str(output))} file format format document"
            )
            commands.append(f"set d to document {_apple_string(output.name)}")
        elif action == "text" and output is not None:
            commands.extend(
                [
                    "set table_count to count of tables of d",
                    f"save as d file name {_apple_string(str(output))} file format format text",
                    f"set d to document {_apple_string(output.name)}",
                ]
            )
        commands.append("close d saving no")
        if action == "text":
            commands.append("return table_count as string")
        body = "\n".join(commands)
        seconds = max(1, int(self.timeout_s))
        return (
            f"with timeout of {seconds} seconds\n"
            'tell application "Microsoft Word"\n'
            f"{body}\nend tell\nend timeout"
        )

    def _close_failed_open(self, copy: Path, output: Path | None = None) -> str:
        names = [copy.name] if output is None else [output.name, copy.name]
        closers = "\n".join(
            f"if exists document {_apple_string(name)} then "
            f"close document {_apple_string(name)} saving no"
            for name in names
        )
        script = f'tell application "Microsoft Word"\n{closers}\nend tell'
        try:
            result = self.runner(script, self.timeout_s + 5)
            if result.returncode == 0:
                return ""
            detail = result.stderr or result.stdout
        except Exception as exc:
            detail = str(exc)
        try:
            self._force_quit()
        except (OfficeError, OSError, subprocess.SubprocessError) as exc:
            raise OfficeError("word_restart", f"{detail}; cleanup: {exc}") from exc
        return f"; cleanup forced Word quit: {detail}"

    def _failed_script(self, result: OsaResult, copy: Path, output: Path | None) -> None:
        if "-1743" in result.stderr:
            raise OfficeError(
                "word_permission",
                "Grant Automation in System Settings → Privacy & Security → "
                "Automation → the calling app → Microsoft Word. " + result.stderr,
            )
        if "-1712" in result.stderr:
            try:
                self._force_quit()
            except (OfficeError, OSError, subprocess.SubprocessError) as quit_exc:
                raise OfficeError(
                    "word_restart", f"{result.stderr}; force quit: {quit_exc}"
                ) from quit_exc
            raise TimeoutError(result.stderr)
        detail = result.stderr or result.stdout
        try:
            detail += self._close_failed_open(copy, output)
        except OfficeError as exc:
            raise OfficeError("word_restart", f"{detail}; cleanup: {exc.detail}") from exc
        raise OfficeError("word_automation", detail)

    def _copy_result(
        self, action: str, source: Path, target: Path | None, result: OsaResult
    ) -> int | None:
        if target is not None:
            if not source.is_file():
                code = {"pdf": "word_pdf", "docx": "word_docx", "text": "word_text"}[action]
                raise OfficeError(code, f"Word reported success without a {source.suffix} file")
            shutil.copy2(source, target)
        if action == "text":
            try:
                return int(result.stdout.strip())
            except ValueError as exc:
                raise OfficeError("word_text", f"Invalid table count: {result.stdout!r}") from exc
        return None

    def _attempt(self, action: str, document: Path, target: Path | None) -> int | None:
        folder = self.work_root / str(uuid.uuid4())
        folder.mkdir(parents=True)
        copy = folder / f"{uuid.uuid4()}-{document.name}"
        suffix = {"pdf": ".pdf", "docx": ".docx", "text": ".txt"}.get(action)
        basename = uuid.uuid4().hex if action in {"docx", "text"} else "converted"
        output = folder / f"{basename}{suffix}" if suffix is not None else None
        try:
            shutil.copy2(document, copy)
            try:
                result = self.runner(self._script(action, copy, output), self.timeout_s + 5)
            except (TimeoutError, subprocess.TimeoutExpired) as exc:
                try:
                    self._force_quit()
                except (OfficeError, OSError, subprocess.SubprocessError) as quit_exc:
                    raise OfficeError("word_restart", f"{exc}; force quit: {quit_exc}") from exc
                raise
            except OSError as exc:
                raise OfficeError("word_launch", str(exc)) from exc
            except Exception as exc:
                try:
                    detail = str(exc) + self._close_failed_open(copy, output)
                except OfficeError as cleanup_exc:
                    raise OfficeError(
                        "word_restart", f"{exc}; cleanup: {cleanup_exc.detail}"
                    ) from exc
                raise OfficeError("word_automation", detail) from exc
            if result.returncode:
                self._failed_script(result, copy, output)
            if action == "toc":
                shutil.copy2(copy, document)
            if output is not None:
                return self._copy_result(action, output, target, result)
            return None
        finally:
            shutil.rmtree(folder)

    def _perform(self, action: str, document: Path, target: Path | None = None) -> int | None:
        if not self.app.is_dir():
            raise OfficeError("word_missing", f"Word is missing at {self.app}")
        with self._lock, self._process_lock():
            for attempt in range(2):
                try:
                    return self._attempt(action, document, target)
                except (TimeoutError, subprocess.TimeoutExpired) as exc:
                    detail = str(exc)
                    if isinstance(exc, subprocess.TimeoutExpired) and exc.stderr:
                        detail += " stderr: " + exc.stderr.decode(errors="replace")
                    if attempt == 1:
                        raise OfficeError("word_timeout", detail) from exc
                    try:
                        self._restart()
                    except (OSError, subprocess.SubprocessError, OfficeError) as restart_exc:
                        raise OfficeError(
                            "word_restart", f"{detail}; restart: {restart_exc}"
                        ) from exc

    def update_toc_pages(self, docx: Path) -> None:
        self._perform("toc", docx)

    def render_pdf(self, docx: Path, pdf: Path) -> None:
        self._perform("pdf", docx, pdf)

    def convert_doc(self, doc: Path, out_docx: Path) -> None:
        self._perform("docx", doc, out_docx)

    def doc_text(self, doc: Path) -> DocText:
        with TemporaryDirectory() as directory:
            text_path = Path(directory) / "original.txt"
            tables = self._perform("text", doc, text_path)
            raw = text_path.read_bytes()
        content = decode_word_text(raw)
        if tables is None:
            raise OfficeError("word_text", "Word did not return a table count")
        return DocText(content, tables)

    def open_check(self, docx: Path) -> None:
        """Check that Word opens and closes; only a human can rule out a repair prompt."""
        self._perform("open", docx)
