"""Level-1 structure check of the auditor's 2026 chapter-six method."""

from pathlib import Path

import pytest
from docx import Document
from docx.oxml.ns import qn
from tests.golden.cases import case_path

from ema.audit.base_units import heading_spans_document

pytestmark = pytest.mark.golden
PROFILES = ("audit-01", "audit-02", "audit-03", "audit-04")


@pytest.mark.parametrize("profile", PROFILES)
def test_trb_method_and_measure_table_headers(reference_library: Path, profile: str) -> None:
    document = Document(str(case_path(profile)))
    body = list(document.element.body)
    spans = heading_spans_document(document)
    method = next((start, end) for item, start, end in spans if item.section_id == "ch6.indicatori")
    math = "".join(
        node.text or ""
        for element in body[method[0] : method[1]]
        for node in element.iter(qn("m:t"))
    )
    assert "TRB=CIVan[ani]" in "".join(math.split()), profile
    measures = [(start, end) for item, start, end in spans if item.section_id == "ch6.measure"]
    assert measures, profile
    for start, end in measures:
        tables = [element for element in body[start:end] if element.tag == qn("w:tbl")]
        synthesis = [
            table
            for table in tables
            if [len(row.findall(qn("w:tc"))) for row in table.findall(qn("w:tr"))[:2]] == [5, 6]
        ]
        assert len(synthesis) == 1, profile
        assert len(synthesis[0].findall(qn("w:tr"))) >= 3, profile
