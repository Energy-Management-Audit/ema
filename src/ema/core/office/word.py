"""Supervised Word for Mac operations on isolated document copies."""

from __future__ import annotations

import fcntl
import shutil
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ema.core.office.errors import OfficeError


@dataclass(frozen=True)
class OsaResult:
    returncode: int
    stdout: str
    stderr: str


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

    def __init__(
        self,
        app: Path = Path("/Applications/Microsoft Word.app"),
        timeout_s: float = 120,
        runner: OsaRunner | None = None,
    ) -> None:
        self.app = app
        self.timeout_s = timeout_s
        self.runner = runner or _run_osa
        self.work_root = Path.home() / "Library/Containers/com.microsoft.Word/Data/Ema"

    @contextmanager
    def _process_lock(self):
        self.work_root.mkdir(parents=True, exist_ok=True)
        with (self.work_root / ".word.lock").open("a+b") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

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

    def _script(self, action: str, document: Path, pdf: Path | None = None) -> str:
        path = _apple_string(str(document))
        name = _apple_string(document.name)
        commands = [
            f"open (POSIX file {path})",
            f"set d to document {name}",
        ]
        if action == "toc":
            commands.extend(["update page numbers of table of contents 1 of d", "save d"])
        elif action == "pdf" and pdf is not None:
            commands.append(f"save as d file name {_apple_string(str(pdf))} file format format PDF")
        commands.append("close d saving no")
        body = "\n".join(commands)
        seconds = max(1, int(self.timeout_s))
        return (
            f"with timeout of {seconds} seconds\n"
            'tell application "Microsoft Word"\n'
            f"{body}\nend tell\nend timeout"
        )

    def _close_failed_open(self, copy: Path) -> str:
        script = (
            'tell application "Microsoft Word"\n'
            f"close document {_apple_string(copy.name)} saving no\n"
            "end tell"
        )
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

    def _failed_script(self, result: OsaResult, copy: Path) -> None:
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
            detail += self._close_failed_open(copy)
        except OfficeError as exc:
            raise OfficeError("word_restart", f"{detail}; cleanup: {exc.detail}") from exc
        raise OfficeError("word_automation", detail)

    def _attempt(self, action: str, docx: Path, pdf: Path | None) -> None:
        folder = self.work_root / str(uuid.uuid4())
        folder.mkdir(parents=True)
        copy = folder / f"{uuid.uuid4()}-{docx.name}"
        output = folder / "render.pdf" if pdf is not None else None
        try:
            shutil.copy2(docx, copy)
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
                    detail = str(exc) + self._close_failed_open(copy)
                except OfficeError as cleanup_exc:
                    raise OfficeError(
                        "word_restart", f"{exc}; cleanup: {cleanup_exc.detail}"
                    ) from exc
                raise OfficeError("word_automation", detail) from exc
            if result.returncode:
                self._failed_script(result, copy)
            if action == "toc":
                shutil.copy2(copy, docx)
            if action == "pdf" and pdf is not None and output is not None:
                if not output.is_file():
                    raise OfficeError("word_pdf", "Word reported success without a PDF")
                shutil.copy2(output, pdf)
        finally:
            shutil.rmtree(folder)

    def _perform(self, action: str, docx: Path, pdf: Path | None = None) -> None:
        if not self.app.is_dir():
            raise OfficeError("word_missing", f"Word is missing at {self.app}")
        with self._lock, self._process_lock():
            for attempt in range(2):
                try:
                    self._attempt(action, docx, pdf)
                    return
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

    def open_check(self, docx: Path) -> None:
        """Check that Word opens and closes; only a human can rule out a repair prompt."""
        self._perform("open", docx)
