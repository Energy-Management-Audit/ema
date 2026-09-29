"""De-identified ch. 2-3 structure comparison for S14 golden evidence."""

from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from tests.golden.cases import case_path

from ema.audit.headings import map_headings


def auditor_structure(root: Path) -> dict[str, dict[str, object]]:
    profiles = ("audit-01", "audit-02", "audit-03", "audit-04", "audit-05")
    result: dict[str, dict[str, object]] = {}
    for profile in profiles:
        path = case_path(profile)
        mapped = map_headings(path, profile)
        chapter_ids = {
            item.section_id for item in mapped.mapped if item.section_id.startswith(("ch2", "ch3"))
        }
        assert chapter_ids, path.name
        document = Document(str(path))
        body = list(document.element.body)
        paragraphs = document.paragraphs
        locations = {id(element): index for index, element in enumerate(body)}
        sections: dict[str, dict[str, object]] = {}
        for item in mapped.mapped:
            if item.section_id not in {"ch2.date_generale", "ch3.flux"}:
                continue
            start = locations[id(paragraphs[item.heading.index]._p)]
            next_heading = next(
                (
                    other
                    for other in mapped.mapped
                    if other.heading.index > item.heading.index
                    and other.heading.level <= item.heading.level
                ),
                None,
            )
            end = (
                locations[id(paragraphs[next_heading.heading.index]._p)]
                if next_heading
                else len(body)
            )
            region = body[start + 1 : end]
            text = " ".join(
                "".join(node.text or "" for node in element.iter(qn("w:t")))
                for element in region
                if element.tag == qn("w:p")
            ).casefold()
            sections[item.section_id] = {
                "paragraphs": sum(
                    bool("".join(node.text or "" for node in element.iter(qn("w:t"))).strip())
                    for element in region
                    if element.tag == qn("w:p")
                ),
                "tables": sum(element.tag == qn("w:tbl") for element in region),
                "figure_or_table_reference": "figura" in text or "tabel" in text,
                "process_stage": "etap" in text or "flux" in text,
            }
        result[profile] = {"sections": len(chapter_ids), "detail": sections}
    return result
