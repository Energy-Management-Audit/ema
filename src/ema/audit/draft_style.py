"""A redacted, runtime-only section example from the reference audit, and its length (#163 D1).

The reference audit is the client's previous audit when the job holds one, else the configured
audit base. A section's example is its own content, without its subsections' (D8), as its
paragraphs, list items and tables in their order: the draft rewrites it in that order (#163 D2).
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import unicodedata
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from ema.audit.base_entry import base_sha
from ema.audit.draft_schema import SECTION_FACTS
from ema.audit.headings import headings, map_headings
from ema.clients.registry import get_client
from ema.core.config import load_settings
from ema.core.errors import EmaError
from ema.core.office.convert import stored_file
from ema.core.office.sniff import FileKind, sniff
from ema.core.workspace import Workspace
from ema.core.workspace.conversion import active_version

PREVIOUS_AUDIT_SLOT = "previous_audit"
_NUMBER = re.compile(r"\d+(?:[.,/–-]\d+)*\s*%?")
_WORD = re.compile(r"\b[A-ZĂÂÎȘȚŞŢ][A-Za-z0-9ĂÂÎȘȚăâîșțŞŢşţ]*\b")
_CAPTION = re.compile(r"^\s*(?:Tabel|Fig)")


@dataclass(frozen=True)
class ExamplePart:
    """One paragraph, list item or table of a section's example; a table by its header row."""

    kind: Literal["body", "bullet", "table"]
    text: str


@dataclass(frozen=True)
class Example:
    parts: tuple[ExamplePart, ...]
    words: int

    @property
    def text(self) -> str:
        return "\n".join(part.text for part in self.parts)


def _fold(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFD", value) if unicodedata.category(char) != "Mn"
    ).casefold()


def _mask_identity(value: str, identity: tuple[str, ...]) -> str:
    folded = ""
    positions: list[int] = []
    for index, char in enumerate(value):
        for normalized in _fold(char):
            folded += " " if normalized.isspace() else normalized
            positions.append(index)
    spans: list[tuple[int, int]] = []
    for term in identity:
        parts = _fold(term).split()
        if parts:
            pattern = r"\s+".join(re.escape(part) for part in parts)
            spans.extend(
                (positions[m.start()], positions[m.end() - 1] + 1)
                for m in re.finditer(pattern, folded)
            )
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    for start, end in reversed(merged):
        value = value[:start] + "{{…}}" + value[end:]
    return value


def _mask_names(value: str) -> str:
    # Sentence-initial names resemble ordinary words, so mask both to avoid a leak.
    return _WORD.sub("{{…}}", value)


def _listed(paragraph: Paragraph) -> bool:
    properties = paragraph._p.pPr  # pyright: ignore[reportPrivateUsage]
    if properties is not None and properties.find(qn("w:numPr")) is not None:
        return True
    style = paragraph.style
    return style is not None and (style.name or "").startswith("List")


def _header(table: Table) -> str:
    """A table's first row, each merged cell once."""
    if not table.rows:
        return ""
    cells: list[str] = []
    for cell in table.rows[0].cells:
        text = " ".join(cell.text.split())
        if text and (not cells or cells[-1] != text):
            cells.append(text)
    return " | ".join(cells)


def _own_parts(base: Path, sections: Collection[str]) -> dict[str, list[ExamplePart]]:
    """Each section's own content in the reference, from its first heading to the next heading,
    in document order; captions and empty paragraphs (figures) left out."""
    document = Document(str(base))
    content = list(document.iter_inner_content())
    # Heading indexes count the body's paragraphs alone; tables sit between them.
    positions = [index for index, item in enumerate(content) if isinstance(item, Paragraph)]
    starts = sorted(positions[item.index] for item in headings(base))
    found: dict[str, list[ExamplePart]] = {}
    for item in map_headings(base, "audit-01").mapped:
        if item.section_id not in sections or item.section_id in found:
            continue
        begin = positions[item.heading.index]
        end = next((index for index in starts if index > begin), len(content))
        parts: list[ExamplePart] = []
        for block in content[begin + 1 : end]:
            if isinstance(block, Table):
                parts.append(ExamplePart("table", _header(block)))
            elif block.text.strip() and not _CAPTION.match(block.text):
                parts.append(ExamplePart("bullet" if _listed(block) else "body", block.text))
        found[item.section_id] = parts
    return found


def style_examples(
    base: Path, identity: tuple[str, ...], sections: Collection[str]
) -> dict[str, Example]:
    """Per section, its redacted own parts in order and their word count before redaction; a
    table counts no words, since the draft writes none."""
    terms = tuple(sorted(identity, key=len, reverse=True))
    return {
        section: Example(
            tuple(
                ExamplePart(
                    part.kind, _mask_names(_NUMBER.sub("{{…}}", _mask_identity(part.text, terms)))
                )
                for part in own
            ),
            sum(len(part.text.split()) for part in own if part.kind != "table"),
        )
        for section, own in _own_parts(base, sections).items()
    }


def style_example(base: Path, identity: tuple[str, ...], section: str) -> str:
    example = style_examples(base, identity, (section,)).get(section)
    return example.text if example is not None else ""


def checked_previous_audit(path: Path) -> Path:
    """A .docx with the own text of at least one ch. 2-3 section; refused before the slot
    changes, so a draft never falls back from the audit the auditor chose."""
    kind = sniff(path).kind
    if kind != FileKind.DOCX:
        raise EmaError(
            "previous_audit_type", "Auditul anterior nu este un document Word .docx.", kind.value
        )
    try:
        parts = _own_parts(path, SECTION_FACTS)
    except Exception as exc:  # python-docx raises many types on a damaged package
        raise EmaError(
            "previous_audit_unusable",
            "Auditul anterior nu poate fi citit.",
            f"{type(exc).__name__}: {exc}",
        ) from exc
    if not any(parts.values()):
        raise EmaError(
            "previous_audit_unusable",
            "Auditul anterior nu are secţiuni din capitolele 2-3.",
            path.name,
        )
    return path


def _previous_identity(version: int, file_sha: str) -> str:
    return f"{PREVIOUS_AUDIT_SLOT}@{version}:{file_sha}"


def _base_identity(ws: Workspace) -> str:
    return f"base:{base_sha(load_settings(ws)) or 'none'}"


def reference_identity(ws: Workspace, job: str, db: sqlite3.Connection) -> str:
    """The current reference of the job's ch. 2-3 drafts, as their fingerprint records it."""
    row = db.execute(
        "SELECT v.version,v.file_sha FROM slots s JOIN slot_versions v ON v.job_id=s.job_id "
        "AND v.slot=s.name AND v.version=s.active_version WHERE s.job_id=? AND s.name=?",
        (job, PREVIOUS_AUDIT_SLOT),
    ).fetchone()
    if row is None:
        return _base_identity(ws)
    return _previous_identity(int(row["version"]), str(row["file_sha"]))


def configured_examples(ws: Workspace, sections: Collection[str]) -> dict[str, Example]:
    settings = load_settings(ws)
    base, identity_file = settings.audit_base_document, settings.audit_base_identity
    if base is None or identity_file is None or not base.is_file() or not identity_file.is_file():
        logging.getLogger(__name__).warning(
            "Audit style example unavailable: audit_base_document or audit_base_identity"
        )
        return {}
    try:
        identity = cast(object, json.loads(identity_file.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise EmaError(
            "audit_base_missing", "Baza auditului nu este configurată.", "audit_base_identity"
        ) from exc
    if not isinstance(identity, list) or not all(
        isinstance(item, str) for item in cast(list[object], identity)
    ):
        raise EmaError(
            "audit_base_missing", "Baza auditului nu este configurată.", "audit_base_identity"
        )
    return style_examples(base, tuple(cast(list[str], identity)), sections)


@dataclass(frozen=True)
class Reference:
    """The reference audit the drafts follow: its identity, an input of each draft, and its
    sections' examples, both from one read of the slot."""

    identity: str
    examples: dict[str, Example]


def reference_examples(ws: Workspace, job: str, sections: Collection[str]) -> Reference:
    """The sections' examples from the client's previous audit when the job holds one, else
    from the configured audit base (#163 D1)."""
    version = active_version(ws, job, PREVIOUS_AUDIT_SLOT)
    if version is None:
        return Reference(_base_identity(ws), configured_examples(ws, sections))
    client, path = stored_file(ws, job, version.file_sha)
    record = get_client(ws, client)
    terms = tuple(str(record[key]) for key in ("name", "cui") if record.get(key))
    return Reference(
        _previous_identity(version.version, version.file_sha),
        style_examples(checked_previous_audit(path), terms, sections),
    )
