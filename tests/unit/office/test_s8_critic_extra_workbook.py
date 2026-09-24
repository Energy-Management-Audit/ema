"""A PIEE chart must not retain an uncounted embedded workbook."""

from pathlib import Path
from zipfile import ZipFile

from ema.core.office.package import REL_PACKAGE, C, P, R, check_standalone


def test_chart_with_two_referenced_workbooks_fails_package_check(tmp_path: Path) -> None:
    docx = tmp_path / "synthetic.docx"
    with ZipFile(docx, "w") as package:
        package.writestr(
            "word/charts/chart1.xml",
            f'<c:chartSpace xmlns:c="{C}" xmlns:r="{R}">'
            '<c:externalData r:id="rId1"/></c:chartSpace>',
        )
        package.writestr(
            "word/charts/_rels/chart1.xml.rels",
            f'<Relationships xmlns="{P}">'
            f'<Relationship Id="rId1" Type="{REL_PACKAGE}" Target="../embeddings/first.xlsx"/>'
            f'<Relationship Id="rId2" Type="{REL_PACKAGE}" Target="../embeddings/extra.xlsx"/>'
            "</Relationships>",
        )
        package.writestr("word/embeddings/first.xlsx", b"synthetic")
        package.writestr("word/embeddings/extra.xlsx", b"synthetic")

    assert any("workbook" in issue.lower() for issue in check_standalone(docx))
