"""An audit base marks unverified values and keeps stable authored text."""

import json
from pathlib import Path

import pytest
from docx import Document

from ema.audit.base_anchor import (
    MARKER,
    anchor_document,
    assert_markers,
    numeric_variable_texts,
    save_anchor_map,
)


def test_anchor_document_replaces_client_and_numeric_content(tmp_path: Path) -> None:
    document = Document()
    document.add_paragraph("Auditor methodology remains fixed.")
    document.add_paragraph("Client Acme used 1234 MWh.")
    document.add_paragraph("Figura 7. Electricity 1234 MWh")
    document.sections[0].header.paragraphs[0].text = "Acme 2025"
    assert numeric_variable_texts(document, ("Acme",)) == (
        "Client Acme used 1234 MWh.",
        "Figura 7. Electricity 1234 MWh",
    )

    anchors = anchor_document(document, "New Client", ("Acme",))
    assert document.paragraphs[0].text == MARKER
    assert document.paragraphs[1].text == MARKER
    assert document.paragraphs[2].text == f"Figura 1. {MARKER}"
    assert document.sections[0].header.paragraphs[0].text == MARKER
    assert_markers(document, anchors)
    assert {anchor.classification for anchor in anchors} == {"fixed", "variable"}

    path = tmp_path / "map.json"
    save_anchor_map(path, "synthetic-hash", anchors)
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["source_sha256"] == "synthetic-hash"
    assert {entry["slot"] for entry in stored["anchors"]} == {anchor.slot for anchor in anchors}

    document.paragraphs[1].text = "unverified 1234"
    with pytest.raises(ValueError, match="missing variable anchors"):
        assert_markers(document, anchors)


def test_anchor_document_requires_nonblank_denylist() -> None:
    with pytest.raises(ValueError, match="denylist is required"):
        anchor_document(Document(), "New Client", ("",))
