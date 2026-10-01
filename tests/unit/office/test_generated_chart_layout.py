"""Generated charts retain annual labels and let Word fit plots and titles."""

from lxml import etree
from test_chart_rewrite_package import package

from ema.core.office.chart_rewrite import rewrite_bar_chart
from ema.core.office.chart_series import Series
from ema.core.office.charts import _column_root, clone_chart
from ema.core.office.package import C, encoded, read_parts, write_parts, xml

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def _source(tmp_path):
    parts = read_parts(package(tmp_path))
    root = xml(parts, "word/charts/chart1.xml")
    plot = root.find(f".//{{{C}}}plotArea")
    layout = etree.SubElement(plot, f"{{{C}}}layout")
    etree.SubElement(layout, f"{{{C}}}manualLayout")
    category = etree.SubElement(plot, f"{{{C}}}catAx")
    text = etree.SubElement(category, f"{{{C}}}txPr")
    etree.SubElement(text, A + "bodyPr", rot="0")
    value = etree.SubElement(plot, f"{{{C}}}valAx")
    title = etree.SubElement(value, f"{{{C}}}title")
    layout = etree.SubElement(title, f"{{{C}}}layout")
    etree.SubElement(layout, f"{{{C}}}manualLayout")
    rich = etree.SubElement(title, f"{{{C}}}tx")
    etree.SubElement(rich, A + "t").text = "old"
    etree.SubElement(value, f"{{{C}}}numFmt", formatCode="#,##0", sourceLinked="1")
    authored = root.find(f".//{{{C}}}ser")
    trend = etree.SubElement(authored, f"{{{C}}}trendline")
    etree.SubElement(trend, f"{{{C}}}trendlineType", val="linear")
    parts["word/charts/chart1.xml"] = encoded(root)
    return parts, encoded(category)


def test_monthly_axis_font_rotation_skip_auto_layout_precision_and_no_gap_trend(tmp_path):
    parts, _ = _source(tmp_path)
    root = _column_root(
        parts,
        "word/charts/chart1.xml",
        [Series("Consum", [str(n) for n in range(12)], [1.5, None] * 6)],
        "tep/lună",
    )
    category = root.find(f".//{{{C}}}catAx")
    assert category.find(f"{{{C}}}tickLblSkip").get("val") == "1"
    text = category.find(f"{{{C}}}txPr")
    assert text.find(A + "bodyPr").get("rot") == "-2700000"
    font = text.find(A + "p/" + A + "pPr/" + A + "defRPr")
    assert font.get("sz") == "1000"
    assert font.find(A + "latin").get("typeface") == "Times New Roman"
    assert root.find(f".//{{{C}}}manualLayout") is None
    assert root.find(f".//{{{C}}}trendline") is None
    assert root.find(f".//{{{C}}}valAx/{{{C}}}numFmt").get("formatCode") == "#,##0.00"


def test_annual_category_style_and_complete_trendline_are_preserved(tmp_path):
    parts, category = _source(tmp_path)
    root = _column_root(
        parts, "word/charts/chart1.xml", [Series("Consum", ["2024", "2025"], [10, 20])], "tep/an"
    )
    assert encoded(root.find(f".//{{{C}}}catAx")) == category
    assert root.find(f".//{{{C}}}trendline") is not None
    assert root.find(f".//{{{C}}}valAx/{{{C}}}numFmt").get("formatCode") == "#,##0"


def test_gap_in_one_series_removes_every_trendline(tmp_path):
    parts, _ = _source(tmp_path)
    root = _column_root(
        parts,
        "word/charts/chart1.xml",
        [
            Series("A", ["2024", "2025"], [1, 2]),
            Series("B", ["2024", "2025"], [None, 2]),
        ],
        "tep/an",
    )
    assert root.find(f".//{{{C}}}trendline") is None


def test_authored_rewrite_and_clone_reset_value_layout_with_a_gap(tmp_path):
    parts, _ = _source(tmp_path)
    root = xml(parts, "word/charts/chart1.xml")
    category = root.find(f".//{{{C}}}catAx")
    category_title = etree.SubElement(category, f"{{{C}}}title")
    etree.SubElement(etree.SubElement(category_title, f"{{{C}}}layout"), f"{{{C}}}manualLayout")
    title = etree.SubElement(root.find(f"{{{C}}}chart"), f"{{{C}}}title")
    etree.SubElement(etree.SubElement(title, f"{{{C}}}layout"), f"{{{C}}}manualLayout")
    parts["word/charts/chart1.xml"] = encoded(root)
    document = xml(parts, "word/document.xml")
    bookmark = document.find(
        ".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}bookmarkStart"
    )
    bookmark.set(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}name", "_ema_chart_1"
    )
    parts["word/document.xml"] = encoded(document)
    series = [Series("Consum", ["2024", "2025"], [None, 2])]
    source = tmp_path / "authored.docx"
    write_parts(parts, source)
    output = tmp_path / "clone.docx"
    cloned_part = clone_chart(
        source, "word/charts/chart1.xml", series, None, output, generated_layout=True
    )
    cloned = xml(read_parts(output), cloned_part)
    rewritten_part = rewrite_bar_chart(parts, "chart_1", tuple(series))
    rewritten = xml(parts, rewritten_part)
    assert cloned.find(f".//{{{C}}}plotArea/{{{C}}}layout/{{{C}}}manualLayout") is None
    assert cloned.find(f".//{{{C}}}valAx/{{{C}}}title/{{{C}}}layout") is None
    assert cloned.find(f".//{{{C}}}catAx/{{{C}}}title/{{{C}}}layout/{{{C}}}manualLayout") is None
    assert cloned.find(f"{{{C}}}chart/{{{C}}}title/{{{C}}}layout") is not None
    assert cloned.find(f".//{{{C}}}valAx/{{{C}}}scaling/{{{C}}}min").get("val") == "0"
    assert rewritten.find(f".//{{{C}}}plotArea/{{{C}}}layout") is None
    assert rewritten.find(f".//{{{C}}}valAx/{{{C}}}title/{{{C}}}layout") is None
    assert rewritten.find(f".//{{{C}}}catAx/{{{C}}}title/{{{C}}}layout") is not None
    assert rewritten.find(f"{{{C}}}chart/{{{C}}}title/{{{C}}}layout") is not None
    assert cloned.find(f".//{{{C}}}trendline") is None
    assert rewritten.find(f".//{{{C}}}trendline") is not None


def test_generated_layout_keeps_chart_title_and_uses_twelve_categories(tmp_path):
    parts, _ = _source(tmp_path)
    root = xml(parts, "word/charts/chart1.xml")
    title = etree.SubElement(root.find(f"{{{C}}}chart"), f"{{{C}}}title")
    etree.SubElement(etree.SubElement(title, f"{{{C}}}layout"), f"{{{C}}}manualLayout")
    parts["word/charts/chart1.xml"] = encoded(root)
    generated = _column_root(
        parts,
        "word/charts/chart1.xml",
        [Series("Consum", [str(i) for i in range(12)], [1] * 12)],
        "MWh",
    )
    assert (
        generated.find(f"{{{C}}}chart/{{{C}}}title/{{{C}}}layout/{{{C}}}manualLayout") is not None
    )
    assert generated.find(f".//{{{C}}}catAx/{{{C}}}tickLblSkip").get("val") == "1"
    short = _column_root(
        parts, "word/charts/chart1.xml", [Series("Consum", ["2024", "2025"], [1, 2])], "MWh/lună"
    )
    assert short.find(f".//{{{C}}}catAx/{{{C}}}tickLblSkip") is None
