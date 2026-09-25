"""Synthetic chart rewrite and removal through a bookmarked package."""

from docx import Document
from lxml import etree

from ema.core.office.chart_rewrite import remove_chart, rewrite_bar_chart
from ema.core.office.charts import Series, read_series
from ema.core.office.package import C, P, R, check_standalone, read_parts, write_parts


def package(tmp_path):
    source = tmp_path / "synthetic.docx"
    Document().save(source)
    parts = read_parts(source)
    chart = f"""<c:chartSpace xmlns:c="{C}" xmlns:r="{R}">
    <c:chart><c:plotArea><c:barChart><c:barDir val="col"/><c:grouping val="clustered"/>
    <c:ser><c:idx val="0"/><c:order val="0"/>
    <c:tx><c:strRef><c:f>Sheet1!$B$1</c:f><c:strCache><c:ptCount val="1"/>
    <c:pt idx="0"><c:v>Șir</c:v></c:pt></c:strCache></c:strRef></c:tx>
    <c:cat><c:strRef><c:f>Sheet1!$A$2:$A$3</c:f><c:strCache><c:ptCount val="2"/>
    <c:pt idx="0"><c:v>Ian</c:v></c:pt><c:pt idx="1"><c:v>Feb</c:v></c:pt>
    </c:strCache></c:strRef></c:cat>
    <c:val><c:numRef><c:f>Sheet1!$B$2:$B$3</c:f><c:numCache>
    <c:formatCode>0.00</c:formatCode><c:ptCount val="2"/>
    <c:pt idx="0"><c:v>1.234567</c:v></c:pt><c:pt idx="1"><c:v>2.5</c:v></c:pt>
    </c:numCache></c:numRef></c:val></c:ser><c:gapWidth val="150"/>
    </c:barChart></c:plotArea></c:chart>
    <c:externalData r:id="rId1"><c:autoUpdate val="0"/></c:externalData>
    </c:chartSpace>"""
    parts["word/charts/chart1.xml"] = chart.encode()
    parts["word/charts/_rels/chart1.xml.rels"] = (
        f'<Relationships xmlns="{P}"><Relationship Id="rId1" Type="{R}/oleObject" '
        'Target="https://example.invalid/book.xls" TargetMode="External"/>'
        '<Relationship Id="rId2" Type="http://schemas.microsoft.com/office/2011/'
        'relationships/chartStyle" Target="style1.xml"/></Relationships>'
    ).encode()
    parts["word/charts/style1.xml"] = b"<style/>"
    root = etree.fromstring(parts["word/_rels/document.xml.rels"])
    etree.SubElement(
        root, f"{{{P}}}Relationship", Id="rId999", Type=f"{R}/chart", Target="charts/chart1.xml"
    )
    parts["word/_rels/document.xml.rels"] = etree.tostring(root)
    document = etree.fromstring(parts["word/document.xml"])
    body = document.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}body")
    drawing = etree.fromstring(f"""<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
      xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"
      w14:paraId="10000000" w14:textId="10000001" xmlns:r="{R}" xmlns:c="{C}"
      xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">
      <w:bookmarkStart w:id="42" w:name="_RefSource"/>
      <w:r><w:drawing><wp:inline><wp:docPr id="1" name="Chart"/>
      <c:chart r:id="rId999"/></wp:inline></w:drawing></w:r>
      <w:bookmarkEnd w:id="42"/></w:p>""")
    body.insert(0, drawing)
    parts["word/document.xml"] = etree.tostring(document)
    types = etree.fromstring(parts["[Content_Types].xml"])
    etree.SubElement(
        types,
        "{http://schemas.openxmlformats.org/package/2006/content-types}Override",
        PartName="/word/charts/chart1.xml",
        ContentType="application/vnd.openxmlformats-officedocument.drawingml.chart+xml",
    )
    etree.SubElement(
        types,
        "{http://schemas.openxmlformats.org/package/2006/content-types}Override",
        PartName="/word/charts/style1.xml",
        ContentType="application/vnd.ms-office.chartstyle+xml",
    )
    parts["[Content_Types].xml"] = etree.tostring(types)
    write_parts(parts, source)
    return source


def test_rewrite_and_remove_chart_by_bookmark(tmp_path):
    source = package(tmp_path)
    parts = read_parts(source)
    document = etree.fromstring(parts["word/document.xml"])
    bookmark = next(
        document.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}bookmarkStart")
    )
    bookmark.set(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}name", "_ema_chart_1"
    )
    parts["word/document.xml"] = etree.tostring(document)
    part = rewrite_bar_chart(
        parts,
        "chart_1",
        (Series("Updated", ["Ian", "Feb"], [3.5, None]),),
        cache_name_override="Filed source",
    )
    assert part == "word/charts/chart1.xml"
    rewritten = tmp_path / "rewritten.docx"
    write_parts(parts, rewritten)
    assert read_series(rewritten, part)[0].values == [3.5, None]
    assert read_series(rewritten, part)[0].name == "Filed source"
    assert check_standalone(rewritten) == []

    removed = remove_chart(parts, "chart_1")
    assert removed == part
    assert part not in parts
    assert b"_ema_chart_1" not in parts["word/document.xml"]
    assert b"/word/charts/chart1.xml" not in parts["[Content_Types].xml"]
