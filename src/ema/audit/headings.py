"""Outline-based heading extraction and auditable catalogue mapping."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from docx import Document
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

from ema.audit.catalogue import CATALOGUE, NOT_SECTIONS, Section


@dataclass(frozen=True)
class Heading:
    level: int
    text: str
    path: tuple[str, ...]
    index: int


@dataclass(frozen=True)
class MappedHeading:
    heading: Heading
    section_id: str
    slots: tuple[tuple[str, str], ...] = ()
    template: str | None = None

    @property
    def safe_text(self) -> str:
        if self.template is None:
            return self.heading.text
        return re.sub(r"\{([a-z_]+)\}", r"<\1>", self.template)


@dataclass(frozen=True)
class HeadingMap:
    mapped: tuple[MappedHeading, ...]
    not_sections: tuple[tuple[Heading, str], ...]
    old_template_only: tuple[tuple[Heading, str], ...]
    unmapped: tuple[Heading, ...]
    excluded_captions: tuple[Heading, ...] = ()


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold().replace("ş", "ș").replace("ţ", "ț"))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip().rstrip(" .,:;–-—")


def _outline(paragraph: Paragraph) -> int | None:
    ppr = paragraph._p.pPr  # pyright: ignore[reportPrivateUsage]
    if ppr is not None and (node := ppr.find(qn("w:outlineLvl"))) is not None:
        value = node.get(qn("w:val"))
        return int(value) if value is not None else None
    style = paragraph.style
    seen: set[str] = set()
    while style is not None and style.style_id not in seen:
        seen.add(style.style_id)
        ppr = cast(Any, style.element).pPr
        if ppr is not None and (node := ppr.find(qn("w:outlineLvl"))) is not None:
            value = node.get(qn("w:val"))
            return int(value) if value is not None else None
        style = cast(Any, style).base_style
    return None


_NUMBERED = re.compile(r"^\s*\d+(?:\.\d+)*[.\s-]+")
_CAPTION = re.compile(r"^(?:tabel(?:ul)?|fig(?:ura)?\.?|grafic(?:ul)?)\b", re.IGNORECASE)


def _scan(docx: Path) -> tuple[list[Heading], list[Heading]]:
    tree: list[tuple[int, str]] = []
    result: list[Heading] = []
    captions: list[Heading] = []
    for index, paragraph in enumerate(Document(str(docx)).paragraphs):
        level = _outline(paragraph)
        text = " ".join(paragraph.text.split())
        if level is None or level > 8 or not text:
            continue
        while tree and tree[-1][0] >= level:
            tree.pop()
        item = Heading(level, text, tuple(value for _, value in tree), index)
        if _CAPTION.match(text):
            captions.append(item)
            continue
        style_name = paragraph.style.name if paragraph.style is not None else ""
        if (style_name or "").lower().startswith("toc"):
            continue
        result.append(item)
        tree.append((level, text))
    return result, captions


def headings(docx: Path) -> list[Heading]:
    return _scan(docx)[0]


def _without_number(text: str) -> str:
    return re.sub(r"^(?:capitol(?:ul)?\s+)?\d+(?:\.\d+)*[.\s-]+", "", normalize(text))


def _template(template: str, title: str) -> tuple[tuple[str, str], ...] | None:
    pieces = re.split(r"(\{[a-z_]+\})", normalize(template))
    pattern = (
        "^"
        + "".join("(.+?)" if piece.startswith("{") else re.escape(piece) for piece in pieces)
        + "$"
    )
    match = re.fullmatch(pattern, normalize(title))
    if match is None:
        return None
    keys = [piece[1:-1] for piece in pieces if piece.startswith("{")]
    return tuple(zip(keys, match.groups(), strict=True))


def _folded(text: str) -> tuple[str, list[int]]:
    """`normalize`'s folding, one character at a time, with each folded character's source index."""
    folded: list[str] = []
    index: list[int] = []
    for position, char in enumerate(text):
        lowered = char.casefold().replace("ş", "ș").replace("ţ", "ț")
        for piece in unicodedata.normalize("NFKD", lowered):
            if not unicodedata.combining(piece):
                folded.append(piece)
                index.append(position)
    return "".join(folded), index


def slot_values(template: str, text: str) -> dict[str, str]:
    """Each slot of a heading's catalogue template as the heading itself writes it."""
    numbered = _NUMBERED.match(text)
    offset = numbered.end() if numbered else 0
    folded, index = _folded(text[offset:])
    pieces = re.split(r"(\{[a-z_]+\})", normalize(template))
    pattern = "".join(
        "(.+?)" if piece.startswith("{") else r"\s+".join(map(re.escape, piece.split(" ")))
        for piece in pieces
    )
    match = re.fullmatch(rf"\s*{pattern}[\s.,:;–\-—]*", folded)
    if match is None:
        return {}
    names = [piece[1:-1] for piece in pieces if piece.startswith("{")]
    return {
        name: text[offset + index[match.start(group)] : offset + index[match.end(group) - 1] + 1]
        for group, name in enumerate(names, 1)
    }


def _chapter(title: str) -> int | None:  # noqa: PLR0911
    value = _without_number(title)
    if value.startswith("descrierea si scopul auditului"):
        return 1
    if value.startswith("descrierea si istoricul societatii"):
        return 2
    if value.startswith("descrierea situatiei existente"):
        return 3
    if value.startswith("analiza modului in care se realizeaza consumurile") or value.startswith(
        "analiza consumurilor energetice anuale"
    ):
        return 4
    if value.startswith(("bilanturile energetice", "masuratorile electrice")):
        return 5
    if value.startswith(("masuri de crestere", "masuri propuse pentru cresterea")):
        return 6
    if value.startswith("surse de finantare"):
        return 7
    return None


def _parent_ok(section: Section, parent: str | None) -> bool:
    if section.parent is None:
        return parent is None
    if section.chapter == 4:
        return parent is not None and parent.startswith("ch4")
    if section.id == "ch3.process":
        return parent in ("ch3", "ch3.flux")
    if section.id in {
        "ch3.apa",
        "ch3.electricitate",
        "ch3.gaz",
        "ch3.carburant",
        "ch3.iluminat",
    }:
        return parent in ("ch3", "ch3.utilitati")
    if section.id == "ch6.sinteza":
        return parent in ("ch6", "ch6.specifice")
    return parent == section.parent


def _matches(heading: Heading, chapter: int | None, parent: str | None) -> list[MappedHeading]:
    title = _without_number(heading.text)
    exact = [
        MappedHeading(heading, section.id)
        for section in CATALOGUE
        if section.chapter == chapter
        and _parent_ok(section, parent)
        and normalize(title) in {normalize(item) for item in (section.title, *section.aliases)}
    ]
    if exact:
        return exact
    matches: list[MappedHeading] = []
    broad: list[MappedHeading] = []
    for section in CATALOGUE:
        if section.chapter != chapter or not _parent_ok(section, parent):
            continue
        for template in section.templates:
            slots = _template(template, title)
            if slots is not None:
                target = broad if template.startswith("{") else matches
                target.append(MappedHeading(heading, section.id, slots, template))
    return matches or broad


def _old_only(heading: Heading) -> str | None:
    title = _without_number(heading.text)
    if title.startswith(("masuratorile electrice realizate", "descrierea aparatelor de masura")):
        return "older electrical measurement layout"
    if title.startswith(
        ("rezultatele obtinute in urma masuratorilor", "concluziile obtinute in urma masuratorilor")
    ):
        return "older electrical measurement layout"
    if heading.level == 2 and heading.path and _chapter(heading.path[0]) == 6:
        return "older measure-specific proposal"
    if title.startswith("date privind regimul de lucru si personalul"):
        return "older company-data subsection"
    if title == "situatia contorizarii consumurilor de energie":
        return "older company-data placement"
    return None


def map_headings(docx: Path, audit_id: str) -> HeadingMap:
    mapped: list[MappedHeading] = []
    ignored: list[tuple[Heading, str]] = []
    old: list[tuple[Heading, str]] = []
    unmapped: list[Heading] = []
    chapter: int | None = None
    stack: list[tuple[int, str]] = []
    found, captions = _scan(docx)
    for heading in found:
        while stack and stack[-1][0] >= heading.level:
            stack.pop()
        parent = stack[-1][1] if stack else None
        title = _without_number(heading.text)
        if title in NOT_SECTIONS:
            ignored.append((heading, NOT_SECTIONS[title]))
            continue
        if heading.level == 0:
            chapter = _chapter(heading.text)
        matches = _matches(heading, chapter, parent)
        if len(matches) == 1:
            mapped.append(matches[0])
            stack.append((heading.level, matches[0].section_id))
        elif len(matches) > 1:
            unmapped.append(heading)
        elif audit_id == "CLIENT-A3" and (reason := _old_only(heading)) is not None:
            old.append((heading, reason))
        else:
            unmapped.append(heading)
    return HeadingMap(tuple(mapped), tuple(ignored), tuple(old), tuple(unmapped), tuple(captions))
