"""Infer optional PIEE figure groups from a delivered programme."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from docx.oxml.ns import qn

from ema.core.office.package import read_parts, xml
from ema.energy_data.carriers import Carrier


@dataclass(frozen=True)
class LayoutProfile:
    water_monthly: bool = True
    total_energy_figure: bool = False
    specific_carriers: frozenset[Carrier] | None = None
    separate_pv_figures: bool = True
    annual_fuel_by_type: bool = False
    specific_mix_pies: bool = False
    energy_share_figure: bool = False


def _plain(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(char)
    )


def _captions(path: Path) -> tuple[str, ...]:
    root = xml(read_parts(path), "word/document.xml")
    return tuple(
        _plain("".join(node.text or "" for node in paragraph.iter(qn("w:t"))))
        for paragraph in root.iter(qn("w:p"))
        if re.match(
            r"^\s*(?:fig\.|figura)\s*(?:(?:nr\.|numarul)\s*)?\d+",
            _plain("".join(node.text or "" for node in paragraph.iter(qn("w:t")))),
        )
    )


def _layout_from_captions(captions: tuple[str, ...]) -> LayoutProfile:
    normalized = tuple(_plain(caption) for caption in captions)
    specifics: set[Carrier] = set()
    specific_names = {
        Carrier.electricity_grid: ("electric", "sen"),
        Carrier.electricity_pv: ("fotovolta",),
        Carrier.natural_gas: ("gaz",),
        Carrier.diesel: ("carbur", "motorin"),
        Carrier.coke: ("cocs",),
        Carrier.sunflower_husks: ("coji",),
        Carrier.wood: ("lemn",),
        Carrier.biomass: ("biomas",),
    }
    for caption in normalized:
        if "specific" not in caption or "ponderea consumului specific" in caption:
            continue
        for carrier, terms in specific_names.items():
            if any(term in caption for term in terms):
                specifics.add(carrier)
    return LayoutProfile(
        water_monthly=any("lunar" in caption and "apa" in caption for caption in normalized),
        total_energy_figure=any(
            "energie" in caption
            and "total" in caption
            and "echivalent" in caption
            and "specific" not in caption
            and "ponderea" not in caption
            for caption in normalized
        ),
        specific_carriers=frozenset(specifics),
        separate_pv_figures=any(
            "fotovolta" in caption and "ponderea" in caption for caption in normalized
        ),
        annual_fuel_by_type=sum(
            "anual" in caption and "carbur" in caption and "specific" not in caption
            for caption in normalized
        )
        > 1,
        specific_mix_pies=any("ponderea consumului specific" in caption for caption in normalized),
        energy_share_figure=any("trendul ponderii energiei" in caption for caption in normalized),
    )


def delivered_layout(previous_piee: Path | None) -> LayoutProfile:
    """Use base defaults unless a delivered document supplies figure conventions."""
    return (
        LayoutProfile()
        if previous_piee is None
        else _layout_from_captions(_captions(previous_piee))
    )
