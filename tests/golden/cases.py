"""Resolve neutral golden case codes against the untracked reference library."""

from __future__ import annotations

import argparse
import os
import tomllib
from pathlib import Path
from typing import Any

import pytest


def _mapping() -> tuple[Path, dict[str, Any]]:
    root = Path(os.environ.get("EMA_REFERENCE", "")).expanduser()
    mapping = root / "cases.toml"
    if not os.environ.get("EMA_REFERENCE") or not mapping.is_file():
        pytest.skip(
            "EMA_REFERENCE/cases.toml unavailable; golden not verified", allow_module_level=True
        )
    return root, tomllib.loads(mapping.read_text(encoding="utf-8"))["cases"]


def case_path(code: str, *parts: str) -> Path:
    """Return a case directory or a named path within that case."""
    root, cases = _mapping()
    case = cases[code]
    first = parts[0] if parts else ""
    rest = parts[1:]
    paths = case.get("paths", {})
    relative = paths[first] if parts and first in paths else case["path"]
    trailing = rest if parts and first in paths else parts
    if any(mark in relative for mark in "*?["):
        matches = sorted(root.glob(relative))
        if len(matches) != 1:
            raise ValueError(f"{code}: expected one match for {relative}, found {len(matches)}")
        return matches[0].joinpath(*trailing)
    return root.joinpath(relative, *trailing)


def case_value(code: str, key: str) -> str:
    """Return a real display value kept only in the local mapping."""
    _, cases = _mapping()
    return str(cases[code]["values"][key])


def private_terms() -> tuple[str, ...]:
    root = Path(os.environ["EMA_REFERENCE"]).expanduser()
    mapping = tomllib.loads((root / "cases.toml").read_text(encoding="utf-8"))
    return tuple(mapping["guard"]["terms"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("path", "value"))
    parser.add_argument("code")
    parser.add_argument("parts", nargs="*")
    args = parser.parse_args()
    print(
        case_path(args.code, *args.parts)
        if args.kind == "path"
        else case_value(args.code, args.parts[0])
    )
