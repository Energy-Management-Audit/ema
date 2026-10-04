"""A pie block renders through the shared block writer as a native, embedded chart."""

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from lxml import etree
from openpyxl import load_workbook
from test_chart_rewrite_package import package

from ema.core.office.blocks import ElementLocator, NativeChart, Prototypes, render
from ema.core.office.chart_series import Series
from ema.core.office.package import C, P, R, inspect, read_parts, write_parts

CHART = "word/charts/chart1.xml"
STYLE = "http://schemas.microsoft.com/office/2011/relationships/chartStyle"


def _source(tmp_path: Path) -> tuple[Path, Prototypes]:
    source = package(tmp_path)
    parts = read_parts(source)
    # The style relationship takes rId1, the id pie_root names for its workbook.
    parts["word/charts/_rels/chart1.xml.rels"] = (
        f'<Relationships xmlns="{P}"><Relationship Id="rId1" Type="{STYLE}" Target="style1.xml"/>'
        f'<Relationship Id="rId2" Type="{R}/oleObject" Target="https://example.invalid/b.xls" '
        'TargetMode="External"/></Relationships>'
    ).encode()
    write_parts(parts, source)
    root = etree.fromstring(parts["word/document.xml"])
    paragraph = root.xpath("//*[local-name()='p' and .//*[local-name()='chart']]")[0]
    return source, Prototypes({"chart": paragraph}, chapter=4)


def test_pie_block_renders_one_embedded_related_pie(tmp_path: Path) -> None:
    source, prototypes = _source(tmp_path)
    out = tmp_path / "pie.docx"
    series = Series("Pondere", ["Gaze naturale", "Carburant"], [0.75, 0.25])
    report = render(
        source,
        out,
        ElementLocator(1),
        [NativeChart("chart", CHART, [series], pie="mix")],
        prototypes,
    )
    [part] = report.chart_parts
    parts = read_parts(out)
    chart = etree.fromstring(parts[part])
    ns = {"c": C}
    assert len(chart.xpath("//c:pie3DChart", namespaces=ns)) == 1
    assert not chart.xpath("//c:barChart", namespaces=ns)
    assert chart.xpath("//c:cat//c:pt/c:v/text()", namespaces=ns) == ["Gaze naturale", "Carburant"]
    assert chart.xpath("//c:val//c:pt/c:v/text()", namespaces=ns) == ["0.75", "0.25"]
    ref = next(item for item in inspect(out).charts if item.part == part)
    assert ref.embedded and ref.external is None
    rels = etree.fromstring(parts[part.replace("charts/", "charts/_rels/") + ".rels"])
    types = {rel.get("Id"): rel.get("Type") for rel in rels}
    assert STYLE in types.values() and len(types) == 2
    workbook_rid = chart.find(f"{{{C}}}externalData").get(f"{{{R}}}id")
    assert types[workbook_rid] != STYLE
    document = etree.fromstring(parts["word/document.xml"])
    assert document.xpath(
        f"//*[local-name()='chart' and @r:id='{ref.rel_id}']", namespaces={"r": R}
    )
    with ZipFile(out) as archive:
        book = load_workbook(BytesIO(archive.read(ref.embedded)), data_only=True)
    assert [book["Sheet1"][f"A{row}"].value for row in (2, 3)] == ["Gaze naturale", "Carburant"]
    assert [book["Sheet1"][f"B{row}"].value for row in (2, 3)] == [0.75, 0.25]


@pytest.mark.parametrize(
    "series",
    [
        [Series("Pondere", ["A", "B"], [0.5, None])],
        [Series("Pondere", ["A", "B"], [0.5, 0.5]), Series("Alt", ["A", "B"], [0.5, 0.5])],
        [Series("Share", ["A", "B"], [0.5, 0.5])],
        [Series("Pondere", ["A", "B"], [0.75, 0.75])],
        [Series("Pondere", ["A", "B"], [1.5, -0.5])],
    ],
)
def test_pie_block_needs_one_pondere_series_of_fractions(
    tmp_path: Path, series: list[Series]
) -> None:
    source, prototypes = _source(tmp_path)
    with pytest.raises(ValueError):
        render(
            source,
            tmp_path / "out.docx",
            ElementLocator(1),
            [NativeChart("chart", CHART, series, pie="pv")],
            prototypes,
        )
