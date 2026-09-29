"""Detached native chart blocks for insertion at an arbitrary document location."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import copy
import posixpath
from pathlib import Path

from lxml import etree

from ema.core.office.chart_location import source_paragraph
from ema.core.office.chart_series import Series
from ema.core.office.charts import _column_root, _new_chart, _next_part, _set_series
from ema.core.office.errors import OfficeError
from ema.core.office.package import (
    CT_CHART,
    REL_CHART,
    C,
    P,
    R,
    encoded,
    read_parts,
    relationships,
    rels_path,
    target_part,
    write_parts,
    xml,
)
from ema.core.office.paragraph_properties import keep_paragraph
from ema.core.office.workbook import formula_at, formula_cells

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"


def _chapter_four_style(source_docx: Path) -> tuple[dict[str, bytes], str, etree._Element]:
    parts = read_parts(source_docx)
    for part in sorted(
        name for name in parts if name.startswith("word/charts/chart") and name.endswith(".xml")
    ):
        chart = xml(parts, part)
        if (
            len(chart.findall(f".//{{{C}}}ser")) != 1
            or chart.find(f"{{{C}}}chart/{{{C}}}plotArea/{{{C}}}barChart") is None
        ):
            continue
        try:
            _, _, paragraph, _ = source_paragraph(parts, part)
        except OfficeError:
            continue
        following = paragraph.getnext()
        caption = (
            "".join(node.text or "" for node in following.iter(f"{{{W}}}t"))
            if following is not None and following.tag == f"{{{W}}}p"
            else ""
        )
        if caption.lstrip().startswith("Fig. nr. 4."):
            return parts, part, paragraph
    raise OfficeError("chart_style", "Configured base has no single-series chapter-four bar chart")


def chart_caption_prototype(source_docx: Path) -> etree._Element:
    _, _, paragraph = _chapter_four_style(source_docx)
    caption = paragraph.getnext()
    assert caption is not None
    result = copy.deepcopy(caption)
    keep_paragraph(result, "keepLines")
    return result


def _normalize_style(chart: etree._Element) -> None:  # noqa: C901
    body = chart.find(f"{{{C}}}chart")
    if body is None:
        raise OfficeError("chart_style", "Source chart has no chart body")
    for tag in ("title", "legend"):
        for item in body.findall(f"{{{C}}}{tag}"):
            body.remove(item)
    for item in chart.findall(f"{{{C}}}externalData"):
        chart.remove(item)
    # The imported chart is only a style prototype. Its original ranges can be longer than
    # an annual series; normalize them so the detached builder can size each real series.
    for series in chart.iter(f"{{{C}}}ser"):
        category = series.find(f"{{{C}}}cat/{{{C}}}numRef")
        if category is not None:
            category.tag = f"{{{C}}}strRef"
            cache = category.find(f"{{{C}}}numCache")
            if cache is not None:
                cache.tag = f"{{{C}}}strCache"
                format_code = cache.find(f"{{{C}}}formatCode")
                if format_code is not None:
                    cache.remove(format_code)
        for formula in series.iter(f"{{{C}}}f"):
            if formula.text:
                _, cells = formula_cells(formula.text)
                formula.text = formula_at(formula.text, *cells[0], 1, "row")


def _copy_style_resources(
    source: dict[str, bytes], original: str, parts: dict[str, bytes], part: str
) -> None:
    source_types = xml(source, "[Content_Types].xml")
    types = xml(parts, "[Content_Types].xml")
    etree.SubElement(types, f"{{{CT}}}Override", PartName="/" + part, ContentType=CT_CHART)
    imported_rels = etree.Element(f"{{{P}}}Relationships")
    for rel in relationships(source, original):
        if rel.get("TargetMode") == "External" or rel.get("Type", "").endswith("/package"):
            continue
        resource = target_part(original, rel.get("Target", ""))
        if resource not in source:
            raise OfficeError("chart_style", f"Missing chart style resource: {resource}")
        folder, name = posixpath.split(resource)
        stem, suffix = name.rsplit(".", 1)
        prefix = stem.rstrip("0123456789")
        copied = _next_part(parts, folder, prefix, "." + suffix)
        parts[copied] = source[resource]
        content_type = next(
            (
                item.get("ContentType")
                for item in source_types
                if item.get("PartName") == "/" + resource
            ),
            None,
        )
        if content_type:
            etree.SubElement(
                types, f"{{{CT}}}Override", PartName="/" + copied, ContentType=content_type
            )
        new_rel = copy.deepcopy(rel)
        new_rel.set("Target", posixpath.relpath(copied, posixpath.dirname(part)))
        imported_rels.append(new_rel)
    parts[rels_path(part)] = encoded(imported_rels)
    parts["[Content_Types].xml"] = encoded(types)


def import_chart_style(source_docx: Path, parts: dict[str, bytes]) -> tuple[str, etree._Element]:
    """Bring one ch. 4 chart's appearance and drawing into the working package."""
    source, original, paragraph = _chapter_four_style(source_docx)
    part = _next_part(parts, "word/charts", "chart", ".xml")
    chart = copy.deepcopy(xml(source, original))
    _normalize_style(chart)
    parts[part] = encoded(chart)

    _copy_style_resources(source, original, parts, part)

    document_rels_path = rels_path("word/document.xml")
    document_rels = xml(parts, document_rels_path)
    used = {rel.get("Id") for rel in document_rels}
    rid = next(f"rId{i}" for i in range(1, 100000) if f"rId{i}" not in used)
    etree.SubElement(
        document_rels,
        f"{{{P}}}Relationship",
        Id=rid,
        Type=REL_CHART,
        Target=posixpath.relpath(part, "word"),
    )
    parts[document_rels_path] = encoded(document_rels)
    drawing = copy.deepcopy(paragraph)
    keep_paragraph(drawing, "keepNext")
    chart_nodes = list(drawing.iter(f"{{{C}}}chart"))
    if len(chart_nodes) != 1:
        raise OfficeError("chart_style", "Source drawing needs one chart")
    chart_nodes[0].set(f"{{{R}}}id", rid)
    doc_root = xml(parts, "word/document.xml")
    used_ids = [
        int(node.get("id") or "0")
        for node in doc_root.iter(f"{{{WP}}}docPr")
        if (node.get("id") or "").isdigit()
    ]
    next_id = max(used_ids, default=0) + 1
    for node in drawing.iter(f"{{{WP}}}docPr"):
        node.set("id", str(next_id))
        next_id += 1
    return part, drawing


def clone_chart_detached(
    docx: Path,
    part: str,
    series: list[Series],
    title: str | None,
    out: Path,
    prototype_paragraph: etree._Element,
) -> tuple[str, etree._Element]:
    """Clone a native chart and return its drawing paragraph for caller placement."""
    parts = read_parts(docx)
    root = copy.deepcopy(xml(parts, part))
    _set_series(root, series, title)
    new_part, paragraph = _new_chart(
        parts, part, part, root, detached=True, prototype_paragraph=prototype_paragraph
    )
    write_parts(parts, out)
    return new_part, paragraph


def build_column_chart_detached(
    docx: Path,
    style_source_part: str,
    series: list[Series],
    axis_title: str,
    out: Path,
    prototype_paragraph: etree._Element,
) -> tuple[str, etree._Element]:
    """Build a column chart using S0's style and return its drawing paragraph."""
    parts = read_parts(docx)
    root = _column_root(parts, style_source_part, series, axis_title)
    new_part, paragraph = _new_chart(
        parts,
        style_source_part,
        style_source_part,
        root,
        detached=True,
        prototype_paragraph=prototype_paragraph,
    )
    write_parts(parts, out)
    return new_part, paragraph
