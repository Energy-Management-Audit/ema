"""PIEE case C composition against the delivered native figures and sourced slips."""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import pytest
from docx import Document
from docx.oxml.ns import qn
from tests.golden.cases import case_path
from tests.golden.piee_case_c_comparison import (
    _compare_annual_tables,
    _compare_centralizer,
    _compare_figures,
    _order,
)

from conftest import artifacts_path
from ema.consumption_analysis.analysis import Metric, value
from ema.core.office.package import (
    C,
    check_standalone,
    read_parts,
    xml,
)
from ema.energy_data.carriers import Carrier
from ema.energy_data.source import normal
from ema.piee.compose import compose_draft, load_approved_base
from ema.piee.dataset import PieeData, load
from ema.piee.number import prototype_number
from ema.piee.section_clone_tools import COGEN_BALANCE
from ema.piee.section_clones import COGEN_MIX_SENTENCE

pytestmark = pytest.mark.golden

MISSING_SLOTS = frozenset(
    {
        "body_11",
        "body_14",
        "body_30",
        "body_77",
        "body_78",
        "body_79",
        "body_81",
        "body_165",
        "body_201",
        "body_294",
        "body_363",
        "body_390",
        "body_414",
    }
)


def _data(previous: Path | None) -> PieeData:
    return load(
        2025,
        case_path("piee-case-c", "anexa"),
        None,
        case_path("piee-case-c", "prelucrare"),
        previous,
    )


def _headings(path: Path) -> list[str]:
    return [
        normal(paragraph.text)
        for paragraph in Document(path).paragraphs
        if paragraph.style.name == "Heading 3"
    ]


def _assert_heading_order(path: Path, phrases: tuple[str, ...]) -> None:
    headings = _headings(path)
    positions = [
        next(index for index, heading in enumerate(headings) if phrase in heading)
        for phrase in phrases
    ]
    assert positions == sorted(set(positions))


def test_delivered_layout_composes_case_c_figures_and_missing_markers(  # noqa: PLR0915
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    final = case_path("piee-case-c", "final")
    data = _data(final)
    base = artifacts_path("s8", "base")
    load_approved_base(base)  # The new prototype manifest did not change the approved map.
    prototypes = json.loads((base / "carrier-prototypes.json").read_text(encoding="utf-8"))
    assert set(prototypes) == {"boundaries", "gas", "water", "specific_gas", "gas_annual"}
    assert "annual_list_item" in prototypes["gas"] and "annual_list_item" in prototypes["water"]
    assert {item.key for item in data.disagreements} == {
        "co2.coke.2023",
        "co2.coke.2024",
        "co2.coke.2025",
    }  # S11
    assert data.prelucrare is not None
    assert all(
        data.prelucrare.located[f"turnover.{year}"].label is not None for year in data.dataset.years
    )
    output = tmp_path / "draft.docx"
    status = compose_draft(data, base, output, date(2026, 10, 1))
    assert status.final_ready
    assert not check_standalone(output)
    _compare_figures(output, final, data)
    _compare_annual_tables(final, data)
    _compare_centralizer(output, final, data)
    _assert_heading_order(
        output,
        (
            "energie electrica",
            "gaz natural",
            "cogenerare",
            "carburanti",
            "cocs",
            "apa potabila",
            "apa industriala",
            "apa meteorica",
            "echivalent de energie",
            "specific echivalent de gaz",
            "specific de cocs",
            "specific echivalent de energie totala",
            "specific echivalent de apa",
            "specific de apa industriala",
            "specific de apa meteorica",
            "intensitatea energetica",
            "auditurilor",
            "investitii",
            "impactul de mediu",
        ),
    )
    text = "\n".join(paragraph.text for paragraph in Document(output).paragraphs)
    production = next(iter(data.dataset.production))
    source_production = value(
        data.dataset, data.factors, Metric("production", product=production), 2023
    )[0]
    assert source_production is not None
    produced_amount = prototype_number(source_production, 2)
    assert f"pentru anul 2023 s-au înregistrat {produced_amount} tone/an" in text  # S1
    assert "Evaluția cantității totale" not in text  # S15
    assert COGEN_BALANCE in text
    assert COGEN_MIX_SENTENCE in text
    assert "Evoluția cantității totale de energie echivalentă" in text
    for year in data.dataset.years:
        grid = data.dataset.carriers[Carrier.electricity_grid][year]
        cogen = data.dataset.carriers[Carrier.electricity_cogen][year]
        purchased = (
            grid.annual.value
            if grid.annual is not None
            else sum(reading.value for reading in grid.months.values() if reading.value is not None)
        )
        produced = (
            cogen.annual.value
            if cogen.annual is not None
            else sum(
                reading.value for reading in cogen.months.values() if reading.value is not None
            )
        )
        assert purchased is not None and produced is not None
        total = purchased + produced
        share = round(100 * produced / total)
        assert f"{prototype_number(total, 2)} MWh/an din care {share}%" in text
    assert "tep/mii tone" in text and "m3/tone" in text
    company = str(data.anexa.identity["name"].value)
    assert f"Centralizator al consumurilor de energie la {company}" in text  # S10
    assert f"Impactul de mediu al modului de utilizare a energiei în cadrul {company}" in text
    assert "Adresa sediului social." in text  # S13 keeps the approved base heading.
    assert not any(
        "specific echivalent de energie electrica" in heading
        or "specific echivalent de carbur" in heading
        for heading in _headings(output)
    )  # S9 follows the delivered layout profile.
    parts = read_parts(output)
    assert (
        sum(bool(list(xml(parts, part).iter(f"{{{C}}}pie3DChart"))) for part in _order(output)) == 3
    )

    # The bookmarked copy identifies each red gap without retaining client material.
    monkeypatch.setattr("ema.piee.compose._strip_bookmarks", shutil.copyfile)
    bookmarked = tmp_path / "bookmarked.docx"
    compose_draft(data, artifacts_path("s8", "base"), bookmarked, date(2026, 10, 1))
    slots: set[str] = set()
    absent_identity = 0
    for paragraph in Document(bookmarked).paragraphs:
        if "n.d." not in paragraph.text:
            continue
        assert all(
            str(run.font.color.rgb) == "FF0000"
            for run in paragraph.runs
            if "n.d." in run.text and run.font.color is not None
        )
        names = {
            name.removeprefix("_ema_")
            for mark in paragraph._p.iter(qn("w:bookmarkStart"))
            if (name := mark.get(qn("w:name"), "")).startswith("_ema_")
            and not name.startswith("_ema_prototype_")
        }
        if names:
            slots.update(names)
        else:
            absent_identity += paragraph.text.count("n.d.")
    assert slots == MISSING_SLOTS
    assert absent_identity == 3  # site 2 address and two unsourced site shares


def test_base_layout_composes_all_sourced_case_c_sections(tmp_path: Path) -> None:
    data = _data(None)
    output = tmp_path / "draft.docx"
    status = compose_draft(data, artifacts_path("s8", "base"), output, date(2026, 10, 1))
    assert status.final_ready
    assert not check_standalone(output)
    # 24 production/carrier + 12 water + 3 mix + 8 specific + intensity + CO2 = 49.
    assert len(_order(output)) == 49
    _assert_heading_order(
        output,
        (
            "energie electrica",
            "gaz natural",
            "cogenerare",
            "carburanti",
            "cocs",
            "apa potabila",
            "apa industriala",
            "apa meteorica",
            "echivalent de energie",
            "specific echivalent de energie electrica",
            "specific echivalent de gaz",
            "specific echivalent de carbur",
            "specific de cocs",
            "specific echivalent de energie totala",
            "specific echivalent de apa",
            "specific de apa industriala",
            "specific de apa meteorica",
            "intensitatea energetica",
        ),
    )
    text = "\n".join(paragraph.text for paragraph in Document(output).paragraphs)
    assert "Analiza consumului de cocs" in text
    assert "Analiza consumului de apă industrială" in text
    assert "Analiza consumului de apă meteorică" in text
    assert "energie electrică produsă prin cogenerare" in text
    assert "Analiza consumului de energie electrică produsă prin sisteme fotovoltaice" not in text
