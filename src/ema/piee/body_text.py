"""Sourced prose for the remaining variable PIEE paragraphs."""

from __future__ import annotations

import json
import math
from pathlib import Path

from ema.core.office.anchors import AnchorLedger, find
from ema.core.office.cell_text import set_paragraph_text
from ema.core.office.package import encoded, read_parts, write_parts, xml
from ema.core.office.run_range import TextSpan, replace_spans, visible_text
from ema.energy_data.carriers import Carrier
from ema.piee.chart_plan import BINDINGS, chart_series
from ema.piee.dataset import PieeData
from ema.piee.figure_numbering import REFERENCE
from ema.piee.identity import ownership
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


def render_body_text(source: Path, data: PieeData, output: Path, ledger: AnchorLedger) -> None:
    parts = read_parts(source)
    root = xml(parts, "word/document.xml")
    fuels = _fuel_names(data)
    reference = REFERENCE.search(visible_text(find([root], "body_162")))
    replacements: dict[str, str | None] = {
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
        "body_363": None,
        "body_390": None,
        "body_414": None,
    }
    for slot, replacement in replacements.items():
        set_paragraph_text(find([root], slot), replacement or "n.d.", missing=replacement is None)
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
