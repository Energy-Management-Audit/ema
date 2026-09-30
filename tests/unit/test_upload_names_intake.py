"""Intake labels use the recorded file name with the old slot fallback."""

from ema.core.intake import ItemOutcome, _summary
from ema.core.office.sniff import FileKind


def test_summary_labels_named_and_unnamed_items() -> None:
    named = ItemOutcome(
        "dossier/001",
        1,
        "sha-one",
        FileKind.PDF,
        "failed",
        error_code="read_failed",
        detail="synthetic failure",
        file_name="source.pdf",
    )
    unnamed = ItemOutcome(
        "dossier/002", 2, "sha-two", FileKind.PDF, "detected", warning="synthetic warning"
    )
    summary = _summary([named, unnamed])
    assert summary.item_failures == ["source.pdf: read_failed: synthetic failure"]
    assert summary.warnings == ["dossier/002 v2: synthetic warning"]
