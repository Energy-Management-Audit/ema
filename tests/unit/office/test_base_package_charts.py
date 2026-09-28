"""Chart relationship files belong to chart parts, not to a separate asset relation."""

from test_chart_rewrite_package import package

from ema.audit.base_package import package_issues, scrub_package
from ema.core.office.charts import embed_data
from ema.core.office.package import check_standalone, read_parts, rels_path, write_parts


def test_embedded_chart_relationship_is_not_an_orphan(tmp_path) -> None:
    source = package(tmp_path)
    result = tmp_path / "embedded.docx"
    embed_data(source, "word/charts/chart1.xml", result)
    assert package_issues(result, ("Client Secret",)) == []


def test_scrub_keeps_chart_relationship_and_embedded_workbook(tmp_path) -> None:
    source = package(tmp_path)
    result = tmp_path / "embedded.docx"
    embed_data(source, "word/charts/chart1.xml", result)
    scrub_package(result)
    parts = read_parts(result)
    assert rels_path("word/charts/chart1.xml") in parts
    assert len([name for name in parts if name.startswith("word/embeddings/")]) == 1
    assert check_standalone(result) == []


def test_relationship_without_owner_and_unused_media_are_orphans(tmp_path) -> None:
    source = package(tmp_path)
    result = tmp_path / "embedded.docx"
    embed_data(source, "word/charts/chart1.xml", result)
    parts = read_parts(result)
    parts["word/charts/_rels/missing.xml.rels"] = parts["word/charts/_rels/chart1.xml.rels"]
    parts["word/media/unused.png"] = b"unused"
    write_parts(parts, result)
    issues = package_issues(result, ("Client Secret",))
    assert "orphan asset: word/charts/_rels/missing.xml.rels" in issues
    assert "orphan asset: word/media/unused.png" in issues
