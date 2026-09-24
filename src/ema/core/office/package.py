"""Small OOXML package reader and standalone chart checks."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
P = "http://schemas.openxmlformats.org/package/2006/relationships"
C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REL_CHART = f"{R}/chart"
REL_PACKAGE = f"{R}/package"
CT_CHART = "application/vnd.openxmlformats-officedocument.drawingml.chart+xml"
CT_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass(frozen=True)
class ChartRef:
    part: str
    rel_id: str
    embedded: str | None
    external: str | None


@dataclass(frozen=True)
class PackageReport:
    charts: list[ChartRef]
    external_relationships: list[tuple[str, str, str]]
    charts_without_workbook: list[str]
    orphan_parts: list[str]
    chart_workbook_relationships: dict[str, list[str]]


def rels_path(part: str) -> str:
    folder, name = posixpath.split(part)
    return f"{folder}/_rels/{name}.rels" if folder else f"_rels/{name}.rels"


def owner_part(path: str) -> str:
    folder, name = posixpath.split(path)
    if folder == "_rels":
        return name.removesuffix(".rels")
    return posixpath.join(folder.removesuffix("/_rels"), name.removesuffix(".rels"))


def target_part(owner: str, target: str) -> str:
    if target.startswith("/"):
        return posixpath.normpath(target.lstrip("/"))
    return posixpath.normpath(posixpath.join(posixpath.dirname(owner), target))


def xml(parts: dict[str, bytes], name: str) -> etree._Element:
    return etree.fromstring(parts[name])


def encoded(root: etree._Element) -> bytes:
    return etree.tostring(root, encoding="UTF-8", xml_declaration=True, standalone=True)


def read_parts(docx: Path) -> dict[str, bytes]:
    with ZipFile(docx) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def write_parts(parts: dict[str, bytes], out: Path) -> None:
    with ZipFile(out, "w") as archive:
        for name, content in parts.items():
            archive.writestr(name, content)


def relationships(parts: dict[str, bytes], owner: str) -> list[etree._Element]:
    path = rels_path(owner)
    return list(xml(parts, path)) if path in parts else []


def _graph(parts: dict[str, bytes]) -> tuple[set[str], list[tuple[str, str, str]], dict[str, str]]:
    referenced: set[str] = set()
    external: list[tuple[str, str, str]] = []
    chart_owners: dict[str, str] = {}
    for path in parts:
        if not path.endswith(".rels"):
            continue
        owner = owner_part(path)
        for rel in xml(parts, path):
            kind, target = rel.get("Type", ""), rel.get("Target", "")
            if rel.get("TargetMode") == "External":
                if not kind.endswith("/hyperlink"):
                    external.append((owner, kind, target))
                continue
            resolved = target_part(owner, target)
            referenced.add(resolved)
            if kind == REL_CHART:
                chart_owners[resolved] = rel.get("Id", "")
    return referenced, external, chart_owners


def inspect(docx: Path) -> PackageReport:
    parts = read_parts(docx)
    referenced, external, chart_owners = _graph(parts)
    charts: list[ChartRef] = []
    missing: list[str] = []
    workbook_relationships: dict[str, list[str]] = {}
    chart_parts = sorted(
        p for p in parts if p.startswith("word/charts/chart") and p.endswith(".xml")
    )
    for part in chart_parts:
        root = xml(parts, part)
        ext = root.find(f"{{{C}}}externalData")
        rid = ext.get(f"{{{R}}}id") if ext is not None else None
        link = next((rel for rel in relationships(parts, part) if rel.get("Id") == rid), None)
        embedded = None
        linked = None
        if link is not None:
            if link.get("TargetMode") == "External":
                linked = link.get("Target")
            elif link.get("Type") == REL_PACKAGE:
                embedded = target_part(part, link.get("Target", ""))
        if embedded not in parts:
            missing.append(part)
        charts.append(ChartRef(part, chart_owners.get(part, ""), embedded, linked))
        workbook_relationships[part] = [
            target_part(part, rel.get("Target", ""))
            for rel in relationships(parts, part)
            if rel.get("Type") == REL_PACKAGE
        ]
    orphans = sorted(
        p
        for p in parts
        if (
            (p.startswith("word/charts/chart") and p.endswith(".xml"))
            or p.startswith("word/embeddings/")
        )
        and p not in referenced
    )
    return PackageReport(charts, external, missing, orphans, workbook_relationships)


def check_standalone(docx: Path) -> list[str]:
    report = inspect(docx)
    issues = [
        f"External relationship: {part}: {kind}: {target}"
        for part, kind, target in report.external_relationships
    ]
    issues.extend(
        f"Chart has no embedded workbook: {part}" for part in report.charts_without_workbook
    )
    issues.extend(f"Orphan part: {part}" for part in report.orphan_parts)
    workbooks = [chart.embedded for chart in report.charts if chart.embedded]
    if len(set(workbooks)) != len(workbooks):
        issues.append("Charts share an embedded workbook")
    all_workbooks = [
        workbook
        for chart_workbooks in report.chart_workbook_relationships.values()
        for workbook in chart_workbooks
    ]
    if len(all_workbooks) != len(report.charts):
        issues.append("Each chart must have exactly one embedded workbook relationship")
    if set(all_workbooks) != set(workbooks):
        issues.append("Chart workbook relationships do not match chart references")
    if len(set(all_workbooks)) != len(all_workbooks):
        issues.append("Embedded workbooks must be referenced by exactly one chart")
    return issues
