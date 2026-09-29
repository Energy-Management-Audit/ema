"""Real PIEE inputs enter the shared review and require explicit conflict decisions."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.workspace_jobs import register_client

from ema.core.review import base_readiness, decide, fields
from ema.core.review.models import FieldSpec
from ema.core.workspace import Workspace
from ema.piee.intake import import_piee

pytestmark = pytest.mark.golden


def _only(folder: Path, pattern: str) -> Path:
    files = list(folder.rglob(pattern))
    assert len(files) == 1
    return files[0]


def test_CLIENT-P2_conflicts_require_shared_review_decisions(
    reference_library: Path, tmp_path: Path
) -> None:
    folder = reference_library / "piee/cases/piee-case-b"
    ws = Workspace(tmp_path / "workspace")
    register_client(ws, "golden-client")
    job = import_piee(
        ws,
        "golden-client",
        2025,
        _only(folder, "Anexa*.xlsx"),
        None,
        _only(folder, "*Prelucrare*.xlsx"),
    )
    specs = [
        FieldSpec(key="identity.name", label="Nume client", value_type="text", required=True),
        FieldSpec(
            key="annual.total_tep",
            label="Date anuale total tep",
            value_type="number",
            required=True,
        ),
    ]
    conflicting = fields(ws, job.id, status="conflict")
    assert conflicting
    assert not base_readiness(ws, job.id, specs).final_ok
    for item in conflicting:
        chosen = next(candidate for candidate in item.alternatives if candidate.value == item.value)
        decide(ws, job.id, item.id, "choose", item.revision, "user", alternative=chosen.id)
    assert not fields(ws, job.id, status="conflict")
    assert base_readiness(ws, job.id, specs).final_ok
    assert any(
        item.key == "identity.registrul_comertului" and item.value is None
        for item in fields(ws, job.id)
    )


def test_CLIENT-P1_unit_disagreements_are_review_conflicts(
    reference_library: Path, tmp_path: Path
) -> None:
    folder = reference_library / "piee/cases/piee-case-a"
    ws = Workspace(tmp_path / "workspace")
    register_client(ws, "golden-client")
    job = import_piee(
        ws,
        "golden-client",
        2025,
        _only(folder, "Anexa*.xlsx"),
        _only(folder, "Necesar*.xls"),
        _only(folder, "*Prelucrare*.xls"),
    )
    conflicts = fields(ws, job.id, status="conflict")
    assert conflicts
    assert any(item.key.endswith(".unit") for item in conflicts)
    assert any(item.key.endswith(".payback_years") for item in conflicts)
    assert all(item.key.endswith((".unit", ".payback_years")) for item in conflicts)
    first = conflicts[0]
    preferred = next(
        candidate for candidate in first.alternatives if candidate.value == first.value
    )
    decide(ws, job.id, first.id, "choose", first.revision, "user", alternative=preferred.id)
    assert len(fields(ws, job.id, status="conflict")) == len(conflicts) - 1
