"""Sourced native 3D pies retain approved shares and editable workbooks."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from tests.golden.cases import case_path

from ema.core.office.anchors import AnchorLedger
from ema.core.office.base_map import load as load_map
from ema.core.office.chart_series import read_series
from ema.core.office.package import C, check_standalone, read_parts, xml
from ema.piee.base import build_local_base
from ema.piee.charts import render_bar_charts
from ema.piee.dataset import load
from ema.piee.pies import render_pies

pytestmark = pytest.mark.golden


def _only(folder: Path, pattern: str) -> Path:
    files = list(folder.rglob(pattern))
    assert len(files) == 1
    return files[0]


def _pies(path: Path) -> list[str]:
    parts = read_parts(path)
    return [
        part
        for part in parts
        if part.startswith("word/charts/chart")
        and part.endswith(".xml")
        and list(xml(parts, part).iter(f"{{{C}}}pie3DChart"))
    ]


def test_piee_case_a_pies_match_approved_shares_and_standalone_package(
    reference_library: Path, tmp_path: Path
) -> None:
    sources = reference_library / case_path("piee-case-a")
    data = load(
        2025,
        _only(sources, "Anexa*.xlsx"),
        _only(sources, "Necesar*.xls"),
        _only(sources, "*Prelucrare*.xls"),
    )
    base = _only(reference_library / "piee/finished-programs", "*MODEL_2026.docx")
    build_local_base(base, tmp_path)
    ledger = AnchorLedger(load_map(tmp_path / "base-map.json").variable_slots)
    bars = tmp_path / "bars.docx"
    output = tmp_path / "pies.docx"
    render_bar_charts(tmp_path / "piee-master.docx", data, bars, ledger)
    render_pies(bars, data, output, ledger)
    approved = _only(sources / "generated", "Program de îmbunătățire*.docx")
    generated, expected = _pies(output), _pies(approved)
    assert len(generated) == len(expected) == 6
    expected_series = [read_series(approved, part)[0] for part in expected]
    for part in generated:
        series = read_series(output, part)[0]
        assert any(
            series.categories == other.categories
            and all(
                round(left, 6) == round(right, 6)
                for left, right in zip(series.values, other.values, strict=True)
            )
            for other in expected_series
        )
        root = xml(read_parts(output), part)
        assert [node.get("val") for node in root.iter(f"{{{C}}}rotX")] == ["30"]
        assert [node.get("val") for node in root.iter(f"{{{C}}}perspective")] == ["30"]
        assert [node.get("val") for node in root.iter(f"{{{C}}}legendPos")] == ["r"]
    assert not check_standalone(output)


def test_piee_case_b_raw_mix_pies_follow_delivered_categories_and_available_values(
    reference_library: Path, tmp_path: Path
) -> None:
    sources = reference_library / case_path("piee-case-b")
    previous = case_path("piee-case-b", "final")
    data = load(
        2025,
        _only(sources, "Anexa*.xlsx"),
        None,
        _only(sources, "*Prelucrare*.xlsx"),
        previous,
    )
    assert (data.pie_representation, data.pie_representation_source) == ("raw", "previous_piee")
    base = _only(reference_library / "piee/finished-programs", "*MODEL_2026.docx")
    build_local_base(base, tmp_path)
    ledger = AnchorLedger(load_map(tmp_path / "base-map.json").variable_slots)
    bars = tmp_path / "bars.docx"
    output = tmp_path / "pies.docx"
    render_bar_charts(tmp_path / "piee-master.docx", data, bars, ledger)
    render_pies(bars, data, output, ledger)
    produced = [read_series(output, part)[0] for part in _pies(output)]
    for figure in (22, 24):
        target = read_series(previous, f"word/charts/chart{figure}.xml")[0]
        assert any(
            len(item.values) == len(target.values)
            and all(
                left is not None and right is not None and math.isclose(left, right, rel_tol=1e-9)
                for left, right in zip(item.values, target.values, strict=True)
            )
            for item in produced
        )
    # The source set lacks one category that appears in the authored 2024 pie.
    assert any(len(item.values) == 4 for item in produced)
    assert not check_standalone(output)
