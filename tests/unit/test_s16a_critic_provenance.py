"""Frozen evidence contract must distinguish source provenance."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from ema.core.review.models import Derivation, Evidence, Manual, PdfText, Url


def test_evidence_schema_exposes_frozen_provenance_kinds():
    contract = json.loads(Path("openapi/ema.v1.json").read_text(encoding="utf-8"))
    evidence = contract["components"]["schemas"]["Evidence"]
    provenance = evidence["properties"]["provenance"]
    assert set(provenance["enum"]) == {"document", "online", "calculated", "manual"}
    assert "provenance" in evidence["required"]


def test_provenance_details_are_validated():
    common = {
        "id": "synthetic",
        "retrieved_at": datetime(2026, 1, 1, tzinfo=UTC),
        "highlight": "none",
    }
    Evidence(
        **common,
        provenance="document",
        file_sha="synthetic-version",
        locator=PdfText(page=1, span="synthetic"),
        method="invoice",
    )
    Evidence(
        **common,
        provenance="online",
        locator=Url(url="https://example.test", snapshot_sha="synthetic-snapshot"),
        quote="synthetic quote",
        method="online",
    )
    Evidence(
        **common,
        provenance="calculated",
        method="calc",
        derivation=Derivation(formula_id="f1", inputs=["field-1"], factor_version="v1"),
    )
    Evidence(**common, provenance="manual", locator=Manual(who="user"), method="manual")
    with pytest.raises(ValidationError, match="file version"):
        Evidence(
            **common, provenance="document", locator=PdfText(page=1, span="x"), method="invoice"
        )
    with pytest.raises(ValidationError, match="snapshot"):
        Evidence(**common, provenance="online", locator=Manual(who="user"), method="online")
    with pytest.raises(ValidationError, match="formula"):
        Evidence(**common, provenance="calculated", method="calc")
