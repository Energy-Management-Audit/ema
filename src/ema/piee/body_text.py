"""Sourced prose for the remaining variable PIEE paragraphs."""

from __future__ import annotations

import json
import math
import re
from datetime import date
from pathlib import Path

from ema.core.office.anchors import AnchorLedger, find
from ema.core.office.cell_text import set_paragraph_text
from ema.core.office.package import encoded, read_parts, write_parts, xml
from ema.core.office.run_range import TextSpan, replace_spans, visible_text
from ema.energy_data.carriers import Carrier
from ema.piee.chart_plan import BINDINGS, chart_series
from ema.piee.dataset import PieeData
from ema.piee.figure_numbering import REFERENCE
from ema.piee.identity import SpanText, audit_year, identity_values, ownership
from ema.piee.number import prototype_number
from ema.piee.units import display_unit


def _chart_values(data: PieeData, number: int) -> list[float | None]:
    binding = next(item for item in BINDINGS if item.slot == f"chart_{number}")
    series = chart_series(data, binding)[0]
    return list(series.values) if series is not None else []


def _fuel_names(data: PieeData) -> list[str]:
    return [
        label
        for carrier, label in (
            (Carrier.diesel, "motorină"),
            (Carrier.petrol, "benzină"),
            (Carrier.lpg, "GPL"),
        )
        if carrier in data.dataset.carriers
    ]


def _joined(words: list[str]) -> str:
    return " și ".join((", ".join(words[:-1]), words[-1])) if len(words) > 2 else " și ".join(words)


def _electricity(data: PieeData) -> str | None:
    grid = Carrier.electricity_grid in data.dataset.carriers
    pv = Carrier.electricity_pv in data.dataset.carriers
    if grid and pv:
        return (
            "La nivelul societății s-au înregistrat consumuri de energie electrică "
            "achiziționată din Sistemul Energetic Național, cât și din producția proprie "
            "obținută din parcul fotovoltaic propriu."
        )
    if grid:
        return (
            "La nivelul societății s-a înregistrat consum de energie electrică "
            "achiziționată din Sistemul Energetic Național."
        )
    if pv:
        return (
            "La nivelul societății s-a înregistrat consum de energie electrică "
            "din parcul fotovoltaic propriu."
        )
    return None


def _pv_share(data: PieeData, reference: str | None) -> str | None:
    grid = _chart_values(data, 8)
    pv = _chart_values(data, 12)
    if len(grid) != 3 or len(pv) != 3:
        return None
    shares = [
        100 * solar / (purchased + solar)
        for purchased, solar in zip(grid, pv, strict=True)
        if purchased is not None and solar is not None and purchased + solar > 0
    ]
    if len(shares) != 3:
        return None
    if reference is None:
        raise ValueError("PV share paragraph has no figure reference")
    ceiling = math.ceil(max(shares) * 10) / 10
    if ceiling <= 1:
        return (
            f"Conform {reference} se observă că în perioada de analiză ponderea energiei "
            "electrice consumate din parcul fotovoltaic propriu în total energie electrică "
            f"este redusă, sub {prototype_number(ceiling, 1)}%."
        )
    return (
        f"Conform {reference}, ponderea energiei electrice din parcul fotovoltaic "
        f"propriu în total energie electrică este sub {prototype_number(ceiling, 1)}%."
    )


def _sourced_text(template: str, values: dict[str, str | None]) -> SpanText | None:
    matches = list(re.finditer(r"\{(client|auditor|year)\}", template))
    if all(values[match.group(1)] is None for match in matches):
        return None
    parts: list[str] = []
    missing: list[tuple[int, int]] = []
    cursor = 0
    length = 0
    for match in matches:
        before = template[cursor : match.start()]
        value = values[match.group(1)] or "n.d."
        parts.extend((before, value))
        length += len(before)
        if values[match.group(1)] is None:
            missing.append((length, length + 4))
        length += len(value)
        cursor = match.end()
    parts.append(template[cursor:])
    return SpanText("".join(parts), tuple(missing))


def render_body_text(source: Path, data: PieeData, output: Path, ledger: AnchorLedger) -> None:
    parts = read_parts(source)
    root = xml(parts, "word/document.xml")
    fuels = _fuel_names(data)
    reference = REFERENCE.search(visible_text(find([root], "body_162")))
    auditor = data.anexa.audit.get("auditor")
    values = {
        "client": identity_values(data.anexa, date(data.year, 1, 1))["client_name"],
        "auditor": str(auditor.value).strip() or None if auditor is not None else None,
        "year": audit_year(data.anexa),
    }
    replacements: dict[str, str | SpanText | None] = {
        "body_14": ownership(data.anexa),
        "body_72": f"carburanți ({_joined(fuels)})," if fuels else None,
        "body_83": _electricity(data),
        "body_124": None,
        "body_162": _pv_share(data, reference.group() if reference else None),
        "body_201": None,
        "body_78": None,
        "body_79": None,
        "body_81": None,
        "body_77": None,
        "body_165": None,
        "body_363": _sourced_text(
            "Reprezentanții {client} dau importanță eficienței energetice, fapt dovedit "
            "și prin realizarea lucrării de Audit energetic pe întregul contur energetic "
            "în anul {year} ce aparține societății pentru încadrarea în obligațiile "
            "legii 121/2014.",
            values,
        ),
        "body_390": None,
        "body_414": _sourced_text(
            "Audit energetic pe întregul contur aparținând {client} realizat de {auditor} "
            "în anul {year},",
            values,
        ),
    }
    for slot, replacement in replacements.items():
        paragraph = find([root], slot)
        if isinstance(replacement, SpanText):
            set_paragraph_text(paragraph, replacement.text)
            replace_spans(
                paragraph,
                tuple(TextSpan(start, end, "n.d.", True) for start, end in replacement.missing),
            )
        else:
            set_paragraph_text(paragraph, replacement or "n.d.", missing=replacement is None)
        ledger.record(slot)
    unit = next(iter(data.dataset.production_unit.values()), "")
    if unit:
        paragraph = find([root], "body_48")
        text = visible_text(paragraph)
        old = "tone/lună"
        if text.count(old) != 1:
            raise ValueError("production table caption unit changed in approved base")
        start = text.index(old)
        replace_spans(
            paragraph,
            (TextSpan(start, start + len(old), f"{display_unit(unit)}/lună"),),
        )
        ledger.record("body_48")
    if Carrier.electricity_pv in data.dataset.carriers:
        find([root], "section_electricity_pv_end")
        ledger.record("section_electricity_pv_end")
    if fuels:
        find([root], "section_fuel_start")
        ledger.record("section_fuel_start")
    parts["word/document.xml"] = encoded(root)
    write_parts(parts, output)


def remove_unsourced_recommendation(
    source: Path, manifest: Path, output: Path, ledger: AnchorLedger
) -> None:
    parts = read_parts(source)
    root = xml(parts, "word/document.xml")
    for slot in json.loads(manifest.read_text(encoding="utf-8")):
        paragraph = find([root], slot)
        parent = paragraph.getparent()
        if parent is None:
            raise ValueError("unsourced recommendation has no parent")
        parent.remove(paragraph)
        ledger.record(slot, removed=True)
    parts["word/document.xml"] = encoded(root)
    write_parts(parts, output)
