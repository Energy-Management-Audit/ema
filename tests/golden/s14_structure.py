"""De-identified ch. 2-3 structure comparison for S14 golden evidence."""

from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

from ema.audit.headings import map_headings


def auditor_structure(root: Path) -> dict[str, dict[str, object]]:
    audits = root / "audit/finished-audits"
    patterns = (
        "*AUDIT-01*.docx",
        "*AUDIT-02*.docx",
        "*AUDIT-03*.docx",
        "*AUDIT-04*.docx",
        "Cap 2-3-4 V2.docx",
    )
    result: dict[str, dict[str, object]] = {}
    for pattern in patterns:
        paths = list(audits.glob(pattern))
        assert len(paths) == 1, pattern
        path = paths[0]
        mapped = map_headings(path, "pcm" if "Cap 2-3-4" in pattern else "AUDIT-01")
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
        result[pattern] = {"sections": len(chapter_ids), "detail": sections}
    return result
