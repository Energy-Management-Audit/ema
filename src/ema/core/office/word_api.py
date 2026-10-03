"""Platform selection for the Word operations used by Ema workflows."""

from __future__ import annotations

import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol

from ema.core.config import Settings
from ema.core.office.errors import OfficeError
from ema.core.office.word import DocText, WordMac
from ema.core.office.word_child import WordChild


class WordOffice(Protocol):
    def update_toc_pages(self, docx: Path) -> None: ...

    def render_pdf(self, docx: Path, pdf: Path) -> None: ...

    def convert_doc(self, doc: Path, out_docx: Path) -> None: ...

    def doc_text(self, doc: Path) -> DocText: ...

    def open_check(self, docx: Path) -> None: ...


@contextmanager
def word_session(office: WordOffice) -> Generator[WordOffice]:
    if isinstance(office, WordMac):
        with office.word_session():
            yield office
    else:
        yield office


def word_available(settings: Settings) -> bool:
    if sys.platform == "darwin":
        return settings.word_path.is_dir()
    if sys.platform == "win32":
        return settings.word_path.is_file()
    return False


def worker_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "office-worker"]
    return [sys.executable, "-m", "ema", "office-worker"]


def word_automation(settings: Settings) -> WordOffice:
    if sys.platform == "darwin":
        return WordMac(app=settings.word_path, timeout_s=settings.word_timeout_s)
    if sys.platform == "win32":
        return WordChild(worker_command(), settings.word_timeout_s)
    raise OfficeError("word_missing", f"no Word automation on {sys.platform}")
