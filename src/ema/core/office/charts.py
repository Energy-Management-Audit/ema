"""Native Word chart cache, workbook and part operations."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import copy
import posixpath
import re
from pathlib import Path
from typing import cast

from lxml import etree

from ema.core.office.chart_ids import refresh_unique_ids
from ema.core.office.chart_series import Series, SeriesRefs, _ref, read_series
from ema.core.office.errors import OfficeError
from ema.core.office.package import (
    CT_CHART,
    CT_XLSX,
    REL_CHART,
    REL_PACKAGE,
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
from ema.core.office.workbook import (
    assign_series_formulas,
    build_workbook,
    formula_cells,
)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
__all__ = [
    "Series",
    "SeriesRefs",
    "build_column_chart",
    "clone_chart",
    "embed_all_data",
    "embed_data",
    "read_series",
]


def _elements(root: etree._Element, query: str, **namespaces: str) -> list[etree._Element]:
    return cast("list[etree._Element]", root.xpath(query, namespaces=namespaces))


def _write_cache(ref: etree._Element, values: list[str] | list[float | None]) -> None:
    cache = ref.find(f"{{{C}}}strCache")
    if cache is None:
        cache = ref.find(f"{{{C}}}numCache")
    if cache is None:
        raise OfficeError("chart_cache", "Chart reference has no cache")
    count = cache.find(f"{{{C}}}ptCount")
    if count is None:
        count = etree.SubElement(cache, f"{{{C}}}ptCount")
    count.set("val", str(len(values)))
    for point in cache.findall(f"{{{C}}}pt"):
        cache.remove(point)
    for index, value in enumerate(values):
        if value is None:
            continue
        point = etree.SubElement(cache, f"{{{C}}}pt", idx=str(index))
        etree.SubElement(point, f"{{{C}}}v").text = str(value)


def _next_part(parts: dict[str, bytes], folder: str, prefix: str, suffix: str) -> str:
    index = 1
    while f"{folder}/{prefix}{index}{suffix}" in parts:
        index += 1
    return f"{folder}/{prefix}{index}{suffix}"


def _embed(parts: dict[str, bytes], part: str, root: etree._Element) -> None:
    external_data = root.find(f"{{{C}}}externalData")
    if external_data is None:
        external_data = etree.SubElement(root, f"{{{C}}}externalData")
    rid = external_data.get(f"{{{R}}}id")
    path = rels_path(part)
    rel_root = xml(parts, path) if path in parts else etree.Element(f"{{{P}}}Relationships")
    rel = next((item for item in rel_root if item.get("Id") == rid), None)
    if rel is None:
        used = {item.get("Id") for item in rel_root}
        rid = next(f"rId{i}" for i in range(1, 10000) if f"rId{i}" not in used)
        rel = etree.SubElement(rel_root, f"{{{P}}}Relationship", Id=rid)
        external_data.set(f"{{{R}}}id", rid)
    # The chart's linked OLE relationship becomes an internal package relationship.
    if rel.get("Type") == REL_PACKAGE and rel.get("TargetMode") != "External":
        workbook = target_part(part, rel.get("Target", ""))
    else:
        workbook = _next_part(parts, "word/embeddings", "Ema_Chart", ".xlsx")
    rel.set("Type", REL_PACKAGE)
    rel.set("Target", posixpath.relpath(workbook, posixpath.dirname(part)))
    if "TargetMode" in rel.attrib:
        del rel.attrib["TargetMode"]
    auto = external_data.find(f"{{{C}}}autoUpdate")
    if auto is None:
        auto = etree.SubElement(external_data, f"{{{C}}}autoUpdate")
    auto.set("val", "0")
    parts[workbook] = build_workbook(root)
    parts[path] = encoded(rel_root)
    types = xml(parts, "[Content_Types].xml")
    if not any(item.get("Extension") == "xlsx" for item in types):
        etree.SubElement(types, f"{{{CT}}}Default", Extension="xlsx", ContentType=CT_XLSX)
    parts["[Content_Types].xml"] = encoded(types)
    parts[part] = encoded(root)


def embed_data(docx: Path, part: str, out: Path) -> None:
    parts = read_parts(docx)
    _embed(parts, part, xml(parts, part))
    write_parts(parts, out)


def embed_all_data(docx: Path, out: Path) -> None:
    """Rewrite every authored chart link into its own embedded workbook."""
    parts = read_parts(docx)
    charts = sorted(
        part for part in parts if part.startswith("word/charts/chart") and part.endswith(".xml")
    )
    for part in charts:
        _embed(parts, part, xml(parts, part))
    write_parts(parts, out)


def _source_paragraph(
    parts: dict[str, bytes],
    part: str,
) -> tuple[str, etree._Element, etree._Element, etree._Element]:
    for owner in (p for p in parts if p.startswith("word/") and p.endswith(".xml")):
        rel = next(
            (
                item
                for item in relationships(parts, owner)
                if item.get("Type") == REL_CHART
                and target_part(owner, item.get("Target", "")) == part
            ),
            None,
        )
        if rel is None:
            continue
        root = xml(parts, owner)
        charts = [
            node
            for node in _elements(root, ".//*[local-name()='chart']")
            if node.get(f"{{{R}}}id") == rel.get("Id")
        ]
        if len(charts) != 1:
            continue
        paragraphs = _elements(charts[0], "ancestor::w:p", w=W)
        if len(paragraphs) == 1:
            return owner, root, paragraphs[0], charts[0]
    raise OfficeError("chart_location", f"Chart paragraph not found: {part}")


def _copy_chart_resources(parts: dict[str, bytes], source: str, new_part: str) -> None:
    source_rels = relationships(parts, source)
    new_rels = etree.Element(f"{{{P}}}Relationships")
    types = xml(parts, "[Content_Types].xml")
    for rel in source_rels:
        if rel.get("Type") == REL_PACKAGE or rel.get("TargetMode") == "External":
            continue
        original = target_part(source, rel.get("Target", ""))
        if original not in parts:
            continue
        folder, name = posixpath.split(original)
        prefix = re.sub(r"\d+$", "", name.rsplit(".", 1)[0])
        suffix = "." + name.rsplit(".", 1)[1]
        copied = _next_part(parts, folder, prefix, suffix)
        parts[copied] = parts[original]
        source_type = next(
            (item.get("ContentType") for item in types if item.get("PartName") == "/" + original),
            None,
        )
        if source_type:
            etree.SubElement(
                types, f"{{{CT}}}Override", PartName="/" + copied, ContentType=source_type
            )
        clone_rel = copy.deepcopy(rel)
        clone_rel.set("Target", posixpath.relpath(copied, posixpath.dirname(new_part)))
        new_rels.append(clone_rel)
    parts[rels_path(new_part)] = encoded(new_rels)
    parts["[Content_Types].xml"] = encoded(types)


def _new_chart(
    parts: dict[str, bytes],
    source: str,
    after: str,
    root: etree._Element,
    *,
    detached: bool = False,
    prototype_paragraph: etree._Element | None = None,
) -> tuple[str, etree._Element]:
    new_part = _next_part(parts, "word/charts", "chart", ".xml")
    _copy_chart_resources(parts, source, new_part)
    _embed(parts, new_part, root)
    if prototype_paragraph is None:
        owner, doc_root, paragraph, chart_node = _source_paragraph(parts, after)
    else:
        owner = "word/document.xml"
        doc_root = xml(parts, owner)
        paragraph = prototype_paragraph
        chart_nodes = _elements(paragraph, ".//*[local-name()='chart']")
        if len(chart_nodes) != 1:
            raise OfficeError("chart_location", "Prototype paragraph needs exactly one chart")
        chart_node = chart_nodes[0]
    drawing = next(iter(_elements(chart_node, "ancestor::w:drawing", w=W)), None)
    source_run = drawing.getparent() if drawing is not None else None
    if source_run is None or source_run.tag != f"{{{W}}}r":
        raise OfficeError("chart_location", f"Chart drawing run not found: {after}")
    assert drawing is not None
    clone = etree.Element(f"{{{W}}}p")
    clone.attrib.update(paragraph.attrib)
    properties = paragraph.find(f"{{{W}}}pPr")
    if properties is not None:
        clone.append(copy.deepcopy(properties))
    run = etree.SubElement(clone, f"{{{W}}}r")
    run_properties = source_run.find(f"{{{W}}}rPr")
    if run_properties is not None:
        run.append(copy.deepcopy(run_properties))
    run.append(copy.deepcopy(drawing))
    refresh_unique_ids(root, clone, doc_root)
    parts[new_part] = encoded(root)
    used_ids = {
        int(node.get("id") or "0")
        for node in doc_root.iter(f"{{{WP}}}docPr")
        if (node.get("id") or "").isdigit()
    }
    for node in clone.iter(f"{{{WP}}}docPr"):
        new_id = next(index for index in range(1, 2147483647) if index not in used_ids)
        node.set("id", str(new_id))
        used_ids.add(new_id)
    owner_rels_path = rels_path(owner)
    owner_rels = xml(parts, owner_rels_path)
    used_rids = {item.get("Id") for item in owner_rels}
    rid = next(f"rId{i}" for i in range(1, 100000) if f"rId{i}" not in used_rids)
    etree.SubElement(
        owner_rels,
        f"{{{P}}}Relationship",
        Id=rid,
        Type=REL_CHART,
        Target=posixpath.relpath(new_part, posixpath.dirname(owner)),
    )
    for node in _elements(clone, ".//*[local-name()='chart']"):
        node.set(f"{{{R}}}id", rid)
    if not detached:
        paragraph.addnext(clone)
    parts[owner] = encoded(doc_root)
    parts[owner_rels_path] = encoded(owner_rels)
    types = xml(parts, "[Content_Types].xml")
    etree.SubElement(types, f"{{{CT}}}Override", PartName="/" + new_part, ContentType=CT_CHART)
    parts["[Content_Types].xml"] = encoded(types)
    return new_part, clone


def _set_series(root: etree._Element, series: list[Series], title: str | None) -> None:
    existing = list(root.iter(f"{{{C}}}ser"))
    if len(series) != len(existing):
        raise OfficeError("chart_series", "Series count must match the source chart")
    occupied: dict[tuple[str, int, int], str | float | None] = {}
    source_columns = [
        col
        for node in existing
        for field in ("tx", "cat", "val")
        if (ref := _ref(node, field)) is not None
        if (formula := ref.findtext(f"{{{C}}}f"))
        for _, cells in [formula_cells(formula)]
        for _, col in cells
    ]
    next_column = max(source_columns, default=0) + 1
    for node, item in zip(existing, series, strict=True):
        if len(item.categories) != len(item.values):
            raise OfficeError("chart_series", "Category and value counts differ")
        fields: list[tuple[str, etree._Element, list[str] | list[float | None]]] = []
        for field, values in (("tx", [item.name]), ("cat", item.categories), ("val", item.values)):
            ref = _ref(node, field)
            if ref is None:
                raise OfficeError("chart_series", f"Source series has no {field} reference")
            fields.append((field, ref, values))
        next_column = assign_series_formulas(fields, occupied, next_column)
        for _, ref, values in fields:
            _write_cache(ref, values)
    if title is not None:
        _set_title(root, title)


def _set_title(root: etree._Element, title: str) -> None:
    chart = root.find(f"{{{C}}}chart")
    if chart is None:
        raise OfficeError("chart_title", "Chart body is missing")
    titles = chart.findall(f"{{{C}}}title")
    if not titles:
        a = "http://schemas.openxmlformats.org/drawingml/2006/main"
        title_node = etree.Element(f"{{{C}}}title")
        rich = etree.SubElement(etree.SubElement(title_node, f"{{{C}}}tx"), f"{{{C}}}rich")
        etree.SubElement(rich, f"{{{a}}}bodyPr")
        etree.SubElement(rich, f"{{{a}}}lstStyle")
        paragraph = etree.SubElement(rich, f"{{{a}}}p")
        etree.SubElement(etree.SubElement(paragraph, f"{{{a}}}r"), f"{{{a}}}t").text = title
        chart.insert(0, title_node)
        titles = [title_node]
    texts = _elements(
        titles[0], ".//a:t", a="http://schemas.openxmlformats.org/drawingml/2006/main"
    )
    if texts:
        texts[0].text = title


def clone_chart(docx: Path, part: str, series: list[Series], title: str | None, out: Path) -> str:
    parts = read_parts(docx)
    root = copy.deepcopy(xml(parts, part))
    _set_series(root, series, title)
    new_part, _ = _new_chart(parts, part, part, root)
    write_parts(parts, out)
    return new_part


def build_column_chart(
    docx: Path,
    style_source_part: str,
    series: list[Series],
    axis_title: str,
    out: Path,
    after_part: str | None = None,
) -> str:
    parts = read_parts(docx)
    root = _column_root(parts, style_source_part, series, axis_title)
    new_part, _ = _new_chart(parts, style_source_part, after_part or style_source_part, root)
    write_parts(parts, out)
    return new_part


def _column_root(
    parts: dict[str, bytes], style_source_part: str, series: list[Series], axis_title: str
) -> etree._Element:
    root = copy.deepcopy(xml(parts, style_source_part))
    plot = root.find(f"{{{C}}}chart/{{{C}}}plotArea")
    if plot is None:
        raise OfficeError("chart_style", "Source has no plot area")
    bars = plot.findall(f"{{{C}}}barChart")
    if len(bars) != 1:
        raise OfficeError("chart_style", "Style source must have one column chart")
    bar = bars[0]
    prototypes = bar.findall(f"{{{C}}}ser")
    if not prototypes:
        raise OfficeError("chart_style", "Style source has no series prototype")
    prototype = copy.deepcopy(prototypes[0])
    for item in prototypes:
        bar.remove(item)
    labels = bar.find(f"{{{C}}}dLbls")
    insert_at = list(bar).index(labels) if labels is not None else 2
    for index, _item in enumerate(series):
        node = copy.deepcopy(prototype)
        for tag in ("idx", "order"):
            marker = node.find(f"{{{C}}}{tag}")
            if marker is not None:
                marker.set("val", str(index))
        bar.insert(insert_at + index, node)
    _set_series(root, series, None)
    axes = plot.findall(f"{{{C}}}valAx")
    if axes:
        titles = _elements(
            axes[0],
            "./c:title//a:t",
            c=C,
            a="http://schemas.openxmlformats.org/drawingml/2006/main",
        )
        if titles:
            titles[0].text = axis_title
    return root
