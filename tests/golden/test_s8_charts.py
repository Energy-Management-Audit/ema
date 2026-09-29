"""Real PIEE data rewrites native bars and leaves standalone chart packages."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.golden.cases import case_path

from ema.core.office.anchors import AnchorLedger
from ema.core.office.base_map import load as load_map
from ema.core.office.chart_series import read_series
from ema.core.office.package import inspect
from ema.piee.base import build_local_base
from ema.piee.charts import render_bar_charts
from ema.piee.dataset import load

pytestmark = pytest.mark.golden


def _only(folder: Path, pattern: str) -> Path:
    files = list(folder.rglob(pattern))
    assert len(files) == 1
    return files[0]


def test_piee_case_a_bar_charts_keep_first_ten_approved_value_caches(
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
    output = tmp_path / "charts.docx"
    render_bar_charts(tmp_path / "piee-master.docx", data, output, ledger)
    approved = _only(sources / "generated", "Program de îmbunătățire*.docx")
    for number in range(1, 11):
        part = f"word/charts/chart{number}.xml"
        assert [item.values for item in read_series(output, part)] == [
            item.values for item in read_series(approved, part)
        ]
    report = inspect(output)
    assert not report.external_relationships
    assert not report.charts_without_workbook
    assert not report.orphan_parts
    assert len(ledger.written | ledger.removed) == 31
