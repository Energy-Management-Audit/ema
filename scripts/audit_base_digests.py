"""List the base's text a digest could approve as fixed, for a human review (D1).

Usage: uv run python scripts/audit_base_digests.py <base.docx> <identity.json>
Prints, for every cover or fixed-section paragraph and every header or footer line (as its
`{client}`/`{year}` template, or with each field as `{PAGE}`) that no digest keeps yet and that
holds no identity term, its text and each of its pictures (by image bytes), plus every heading
slot value: slot, section, sha256 and text. The
output names the base's own text: read it in the terminal, never commit it or paste it into a PR.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from docx import Document

from ema.audit.base_anchor import (
    _classification,
    _fixed,
    _paragraph_text,
    _paragraphs,
    _section_by_body_index,
)
from ema.audit.base_numeric import approved_fixed_image, approved_fixed_text
from ema.audit.base_parts import field_line, image_refs, part_classification, templated
from ema.audit.headings import slot_values


def _row(slot: str, section: str, text: str, data: bytes | None = None) -> str:
    digest = hashlib.sha256(text.strip().encode() if data is None else data).hexdigest()
    shown = text.strip() if data is None else "<image bytes>"
    return f"{slot}\t{section}\t{digest}\t{shown}"


def _named(text: str, identity: tuple[str, ...]) -> bool:
    return any(term.casefold() in text.casefold() for term in identity)


def _unreviewed(paragraph: Any, part: Any, slot: str, section: str, text: str) -> Iterator[str]:
    """The text and every picture of a paragraph that no digest keeps yet."""
    if text.strip() and not approved_fixed_text(text):
        yield _row(slot, section, text)
    for ref in image_refs(paragraph):
        data = part.related_parts[ref].blob if ref in part.related_parts else ref.encode()
        if not approved_fixed_image(data):
            yield _row(slot, section, "", data)


def _body(document: Any, identity: tuple[str, ...]) -> Iterator[str]:
    sections, headings = _section_by_body_index(document)
    for index, element in enumerate(document.element.body):
        section = sections.get(index, "front")
        for ordinal, paragraph in enumerate(_paragraphs(element)):
            slot, text = f"body_{index}_{ordinal}", _paragraph_text(paragraph)
            if _named(text, identity):
                continue
            if index in headings and ordinal == 0:
                item = headings[index]
                values = slot_values(item.template, text) if item.template else {}
                for name, value in values.items():
                    yield _row(f"{slot}{{{name}}}", item.section_id, value)
            elif (section == "front" or _fixed(section)) and _classification(
                section, paragraph, identity, heading=False, part=document.part
            ) == "variable":
                yield from _unreviewed(paragraph, document.part, slot, section, text)


def _parts(document: Any, identity: tuple[str, ...]) -> Iterator[str]:
    for kind in ("header", "footer"):
        seen: set[int] = set()
        for section in document.sections:
            part = getattr(section, kind)
            if id(part._element) in seen:
                continue
            seen.add(id(part._element))
            for ordinal, paragraph in enumerate(_paragraphs(part._element)):
                line = field_line(paragraph)
                template = (
                    line if "{" in line else templated(_paragraph_text(paragraph), identity[0])
                )
                classification, _ = part_classification(paragraph, identity, part.part)
                if classification == "variable" and not _named(template, identity):
                    slot = f"{kind}_{len(seen)}_{ordinal}"
                    yield from _unreviewed(paragraph, part.part, slot, "header_footer", template)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    base, identity_file = Path(argv[0]), Path(argv[1])
    identity = tuple(str(term) for term in json.loads(identity_file.read_text(encoding="utf-8")))
    document = Document(str(base))
    print("slot\tsection\tsha256\ttext")
    for row in (*_body(document, identity), *_parts(document, identity)):
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
