"""Typed series read from native Word chart caches."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from ema.core.office.package import C, read_parts, xml
from ema.core.office.workbook import cache_values


@dataclass(frozen=True)
class SeriesRefs:
    name: str | None
    categories: str | None
    values: str | None


@dataclass(frozen=True)
class Series:
    name: str
    categories: list[str]
    values: list[float | None]
    refs: SeriesRefs | None = None


def _ref(ser: etree._Element, field: str) -> etree._Element | None:
    node = ser.find(f"{{{C}}}{field}")
    if node is None:
        return None
    kinds = {f"{{{C}}}strRef", f"{{{C}}}numRef"}
    return next((child for child in node if child.tag in kinds), None)


def _series(root: etree._Element) -> list[Series]:
    result: list[Series] = []
    for ser in root.iter(f"{{{C}}}ser"):
        name_ref, cat_ref, value_ref = (_ref(ser, key) for key in ("tx", "cat", "val"))
        if value_ref is None:
            continue
        values = [float(value) if value is not None else None for value in cache_values(value_ref)]
        name = next((value for value in cache_values(name_ref) if value is not None), "")
        refs = SeriesRefs(
            *(
                ref.findtext(f"{{{C}}}f") if ref is not None else None
                for ref in (name_ref, cat_ref, value_ref)
            )
        )
        result.append(Series(name, [value or "" for value in cache_values(cat_ref)], values, refs))
    return result


def read_series(docx: Path, part: str) -> list[Series]:
    return _series(xml(read_parts(docx), part))
