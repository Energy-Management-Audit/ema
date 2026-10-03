"""A redacted, runtime-only section example from the configured audit base."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import cast

from docx import Document

from ema.audit.headings import map_headings
from ema.core.config import load_settings
from ema.core.errors import EmaError
from ema.core.workspace import Workspace

_NUMBER = re.compile(r"\d+(?:[.,/–-]\d+)*")


def style_example(base: Path, identity: tuple[str, ...], section: str) -> str:
    paragraphs = Document(str(base)).paragraphs
    mapped = map_headings(base, "audit-01").mapped
    heading = next((item.heading for item in mapped if item.section_id == section), None)
    if heading is None:
        return ""
    end = min(
        (
            item.heading.index
            for item in mapped
            if item.heading.index > heading.index and item.heading.level <= heading.level
        ),
        default=len(paragraphs),
    )
    example = "\n".join(p.text for p in paragraphs[heading.index + 1 : end] if p.text.strip())
    for term in sorted(identity, key=len, reverse=True):
        if term.strip():
            example = re.sub(re.escape(term), "{{…}}", example, flags=re.IGNORECASE)
    return _NUMBER.sub("{{…}}", example)


def configured_style_example(ws: Workspace, section: str) -> str:
    settings = load_settings(ws)
    base, identity_file = settings.audit_base_document, settings.audit_base_identity
    if base is None or identity_file is None or not base.is_file() or not identity_file.is_file():
        return ""
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
    return style_example(base, tuple(cast(list[str], identity)), section)
