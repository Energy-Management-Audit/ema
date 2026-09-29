"""Find local private terms in tracked paths and text without storing terms in git."""

from __future__ import annotations

import os
import re
import subprocess
import tomllib
import unicodedata
import zlib
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile


def fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold().replace("ş", "ș").replace("ţ", "ț"))
    return "".join(character for character in normalized if not unicodedata.combining(character))


def pattern(term: str) -> re.Pattern[str]:
    letters = re.findall(r"[a-z0-9]", fold(term))
    return re.compile(r"(?<![a-z0-9])" + r"[\s_-]*".join(map(re.escape, letters)) + r"(?![a-z0-9])")


def scan(path: str, content: str, terms: list[str], allowed: list[str] | None = None) -> list[str]:
    """Report path and line matches, ignoring only explicitly allowed full spans."""
    patterns = [(term, pattern(term)) for term in terms]
    exceptions = [re.compile(value) for value in allowed or []]
    matches: list[str] = []
    for line_number, line in [(0, path), *enumerate(content.splitlines(), 1)]:
        # The Romanian adjective has the same folded spelling as the city.
        folded = fold(re.sub(r"(?<!\w)constantă(?!\w)", "unchanging", line, flags=re.I))
        allowed_spans = [
            span.span() for exception in exceptions for span in exception.finditer(folded)
        ]
        for term, matcher in patterns:
            for found in matcher.finditer(folded):
                if any(
                    start <= found.start() and found.end() <= end for start, end in allowed_spans
                ):
                    continue
                matches.append(f"{path}:{line_number}: {term}")
    return matches


_PDF_STREAM = re.compile(rb"(?s)<<(?P<dictionary>.*?)>>\s*stream\r?\n(?P<body>.*?)\r?\nendstream")


def scan_bytes(
    path: str, content: bytes, terms: list[str], allowed: list[str] | None = None
) -> list[str]:
    """Inspect plain bytes and supported compressed document members."""
    matches = scan(path, content.decode("utf-8", errors="ignore"), terms, allowed)
    if path.lower().endswith((".docx", ".xlsx")):
        try:
            with ZipFile(BytesIO(content)) as archive:
                for member in archive.namelist():
                    matches.extend(
                        scan_bytes(f"{path}!{member}", archive.read(member), terms, allowed)
                    )
        except BadZipFile:
            pass
    elif path.lower().endswith(".pdf"):
        for index, stream in enumerate(_PDF_STREAM.finditer(content), 1):
            if b"/FlateDecode" not in stream.group("dictionary"):
                continue
            try:
                inflated = zlib.decompress(stream.group("body"))
            except zlib.error:
                continue
            matches.extend(
                scan(
                    f"{path}!stream-{index}",
                    inflated.decode("utf-8", errors="ignore"),
                    terms,
                    allowed,
                )
            )
    return matches


def load_guard() -> tuple[list[str], list[str]] | None:
    reference = os.environ.get("EMA_REFERENCE")
    mapping = Path(reference).expanduser() / "cases.toml" if reference else None
    if mapping is None or not mapping.is_file():
        if "CI" in os.environ:
            print("private-term guard skipped: no local mapping")
            return None
        raise FileNotFoundError("private-term guard requires $EMA_REFERENCE/cases.toml locally")
    guard = tomllib.loads(mapping.read_text(encoding="utf-8"))["guard"]
    return guard["terms"], guard.get("allow", [])


def main() -> int:
    try:
        guard = load_guard()
    except FileNotFoundError as error:
        print(error)
        return 1
    if guard is None:
        return 0
    terms, allowed = guard
    files = subprocess.check_output(["git", "ls-files", "-z"]).decode().split("\0")
    matches: list[str] = []
    for path in filter(None, files):
        try:
            content = Path(path).read_bytes()
        except OSError:
            content = b""
        matches.extend(scan_bytes(path, content, terms, allowed))
    for match in matches:
        print(match)
    print(f"private-term guard: {len(matches)} matches")
    return bool(matches)


if __name__ == "__main__":
    raise SystemExit(main())
