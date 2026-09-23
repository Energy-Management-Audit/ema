"""The single path into the packaged resources tree."""

import sys
from pathlib import Path


def resource_path(*parts: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3])) / "resources"
    if any(
        part in {"", ".", ".."} or Path(part).is_absolute() or "/" in part or "\\" in part
        for part in parts
    ):
        raise ValueError("Resource names must be simple path components")
    return root.joinpath(*parts)
