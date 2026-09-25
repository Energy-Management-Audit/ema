"""Fail when a source file grows past the limit in docs/PLAN.md §6.3.

A long file is the usual first sign of a module doing several jobs, so this runs
as a gate rather than as review advice.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

LIMIT = 400
SUFFIXES = {".py", ".ts", ".tsx", ".css"}


def main(argv: list[str]) -> int:
    if not argv:
        argv = (
            subprocess.check_output(
                ["git", "ls-files", "-z", "--", "*.py", "*.ts", "*.tsx", "*.css"]
            )
            .decode()
            .split("\0")
        )
    too_long = []
    for name in argv:
        path = Path(name)
        if path.suffix not in SUFFIXES or not path.is_file():
            continue
        lines = len(path.read_text(encoding="utf-8").splitlines())
        if lines > LIMIT:
            too_long.append((path, lines))

    for path, lines in too_long:
        print(f"{path}: {lines} lines (limit {LIMIT}) — split it before committing")
    return 1 if too_long else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
