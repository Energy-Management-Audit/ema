"""Cross-process advisory lock for destructive filesystem operations."""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock


@contextmanager
def workspace_lock(root: Path) -> Generator[None]:
    lock = FileLock(str(root / ".workspace.lock"))
    with lock:
        yield
