"""The configured audit base's identity: the SHA-256 of its bytes, an input of every section."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from ema.core.config import Settings


@lru_cache(maxsize=16)
def _digest(path: str, mtime_ns: int, size: int) -> str:
    del mtime_ns, size  # the cache key: a rewritten file is hashed again
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def base_sha(settings: Settings) -> str | None:
    """None when no base is configured or it cannot be read; the render refuses those itself."""
    path = settings.audit_base_document
    if path is None:
        return None
    try:
        stat = path.stat()
        return _digest(str(path), stat.st_mtime_ns, stat.st_size)
    except OSError:
        return None
