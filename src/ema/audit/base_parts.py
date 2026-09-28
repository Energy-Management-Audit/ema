"""What the base keeps: header and footer lines, page fields, templates and pictures."""

from __future__ import annotations

import re
from typing import Any, Literal

from docx.oxml.ns import qn

from ema.audit.base_numeric import approved_fixed_image, approved_fixed_text

Binding = Literal["client_name", "address", "report_month", "report_year", "cover_photo"]
_BLIP = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
_VML_IMAGE = "{urn:schemas-microsoft-com:vml}imagedata"
YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
_PAGE_FIELDS = frozenset({"PAGE", "NUMPAGES", "SECTIONPAGES"})


def _pieces(paragraph: Any) -> list[tuple[str, bool]]:
    """The line as its static text and its fields, each field by the first word of its
    instruction; a field's cached result (a number Word recomputes) is left out."""
    pieces: list[tuple[str, bool]] = []
    open_fields: list[list[str]] = []
    for node in paragraph.iter(qn("w:fldChar"), qn("w:instrText"), qn("w:fldSimple"), qn("w:t")):
        kind = node.get(qn("w:fldCharType"))
        if node.tag == qn("w:fldSimple"):
            pieces.append((_field_name(node.get(qn("w:instr")) or ""), True))
        elif node.tag == qn("w:instrText") and open_fields:
            open_fields[-1].append(node.text or "")
        elif node.tag == qn("w:t"):
            simple = any(parent.tag == qn("w:fldSimple") for parent in node.iterancestors())
            if not (open_fields or simple):
                pieces.append((node.text or "", False))
        elif kind == "begin":
            open_fields.append([])
        elif kind == "end" and open_fields:
            code = open_fields.pop()
            if not open_fields:  # a field nested in another one's code is part of that field
                pieces.append((_field_name("".join(code)), True))
    return pieces


def _field_name(instruction: str) -> str:
    words = instruction.split()
    return words[0].upper() if words else ""


def field_line(paragraph: Any) -> str:
    """The line with each field as `{NAME}`: `Pagina {PAGE} din {NUMPAGES}` is her footer."""
    return "".join(f"{{{text}}}" if field else text for text, field in _pieces(paragraph))


def page_line(paragraph: Any) -> bool:
    """Her page numbering: page fields alone, or a reviewed line around them. Any other
    text next to a PAGE field is prose nobody reviewed."""
    pieces = _pieces(paragraph)
    fields = {text for text, field in pieces if field}
    if not fields & _PAGE_FIELDS:
        return False
    static = "".join(text for text, field in pieces if not field)
    return (not static.strip() and fields <= _PAGE_FIELDS) or approved_fixed_text(
        field_line(paragraph)
    )


def templated(text: str, client: str) -> str:
    """Her line with the base client's name as `{client}` and each year as `{year}`."""
    named = re.sub(re.escape(client), "{client}", text, flags=re.IGNORECASE)
    return YEAR.sub("{year}", named)


def _text(paragraph: Any) -> str:
    return "".join(node.text or "" for node in paragraph.iter(qn("w:t")))


def image_refs(paragraph: Any) -> list[str]:
    """Every picture the paragraph embeds or links, DrawingML and VML alike."""
    refs = [
        node.get(qn("r:embed")) or node.get(qn("r:link")) or "" for node in paragraph.iter(_BLIP)
    ]
    refs += [node.get(qn("r:id")) or "" for node in paragraph.iter(_VML_IMAGE)]
    return refs


def images_approved(paragraph: Any, part: Any) -> bool:
    """A picture is kept only by the digest of its own bytes; no text digest covers it."""
    related: dict[str, Any] = part.related_parts if part is not None else {}
    return all(
        ref in related and approved_fixed_image(bytes(related[ref].blob))
        for ref in image_refs(paragraph)
    )


def part_classification(
    paragraph: Any, identity: tuple[str, ...], part: Any
) -> tuple[str, Binding | None]:
    """A header or footer line is kept only when reviewed: her {client}/{year} template, her
    page numbering, a blank line, or text with an approved digest; pictures by bytes."""
    text = _text(paragraph)
    named = any(term.casefold() in text.casefold() for term in identity)
    template = templated(text, identity[0])
    if (
        template != text
        and approved_fixed_text(template)
        and not any(term.casefold() in template.casefold() for term in identity)
    ):
        result: tuple[str, Binding | None] = (
            ("variable", "report_year") if "{year}" in template else ("fixed", None)
        )
    elif not named and (
        not field_line(paragraph).strip() or page_line(paragraph) or approved_fixed_text(text)
    ):
        result = ("fixed", None)
    else:
        result = ("variable", None)
    if result[0] == "fixed" and not images_approved(paragraph, part):
        return "variable", None
    return result
