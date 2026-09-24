"""An authored PIEE bar chart is rewritten through its bookmark and gets Edit Data."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest

from ema.core.office.chart_rewrite import remove_chart, rewrite_bar_chart
from ema.core.office.chart_series import Series, read_series
from ema.core.office.package import C, inspect, read_parts, write_parts, xml
from ema.piee.base import build_local_base

pytestmark = pytest.mark.golden


def test_bar_chart_cache_and_embedded_workbook(reference_library: Path, tmp_path: Path) -> None:
    base = next((reference_library / "piee/finished-programs").glob("*MODEL_2026.docx"))
    build_local_base(base, tmp_path)
    parts = read_parts(tmp_path / "piee-master.docx")
    series = Series(
        "Synthetic production",
        [str(month) for month in range(1, 13)],
        [float(month) for month in range(1, 13)],
    )
    part = rewrite_bar_chart(parts, "chart_1", (series,))
    output = tmp_path / "chart.docx"
    write_parts(parts, output)
    assert read_series(output, part)[0].name == series.name
    assert read_series(output, part)[0].values == series.values
    reference = next(item for item in inspect(output).charts if item.part == part)
    assert reference.external is None
    assert reference.embedded is not None
    root = xml(read_parts(output), part)
    assert not list(root.iter(f"{{{C}}}majorUnit"))
    assert not list(root.iter(f"{{{C}}}minorUnit"))
    assert not list(root.iter(f"{{{C}}}max"))
    assert all(node.get("val") == "0" for node in root.iter(f"{{{C}}}min"))
    with ZipFile(output) as archive, ZipFile(archive.open(reference.embedded)) as workbook:
        assert "xl/workbook.xml" in workbook.namelist()


def test_missing_figure_removes_chart_part(reference_library: Path, tmp_path: Path) -> None:
    base = next((reference_library / "piee/finished-programs").glob("*MODEL_2026.docx"))
    build_local_base(base, tmp_path)
    parts = read_parts(tmp_path / "piee-master.docx")
    removed = remove_chart(parts, "chart_1")
    output = tmp_path / "without-figure.docx"
    write_parts(parts, output)
    assert removed not in read_parts(output)
    assert all(item.part != removed for item in inspect(output).charts)
