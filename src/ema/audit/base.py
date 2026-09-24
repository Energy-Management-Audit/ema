"""Build a de-identified audit draft from a locally configured finished audit."""

from __future__ import annotations

import hashlib
from pathlib import Path

from docx import Document

from ema.audit.base_anchor import (
    anchor_document,
    assert_markers,
    numeric_variable_texts,
    save_anchor_map,
)
from ema.audit.base_package import package_issues, scrub_package
from ema.audit.base_toc import refresh_toc
from ema.audit.base_units import UnitPlan, select_units
from ema.core.config import Settings


def build_base(
    unit_plan: UnitPlan,
    *,
    base_document: Path,
    measurement_prototype: Path,
    output: Path,
    base_identity: tuple[str, ...],
) -> Path:
    """Create a workspace-local DOCX and adjacent anchor map.

    ``base_identity`` has the base client's full name first, followed by all
    local-only identity terms that must not survive in an exported draft.
    """
    if output.resolve() in {base_document.resolve(), measurement_prototype.resolve()}:
        raise ValueError("output must not overwrite a reference audit")
    output.parent.mkdir(parents=True, exist_ok=True)
    document = Document(str(base_document))
    select_units(document, base_document, measurement_prototype, unit_plan)
    numeric_leftovers = numeric_variable_texts(document, base_identity)
    anchors = anchor_document(document, unit_plan.client_name, base_identity)
    refresh_toc(document)
    assert_markers(document, anchors)
    document.save(str(output))
    scrub_package(output)
    issues = package_issues(output, base_identity, numeric_leftovers=numeric_leftovers)
    if issues:
        output.unlink(missing_ok=True)
        raise ValueError("audit base validation failed: " + "; ".join(issues[:8]))
    source_hash = hashlib.sha256(base_document.read_bytes()).hexdigest()
    save_anchor_map(output.with_suffix(".anchors.json"), source_hash, anchors)
    return output


def build_configured_base(
    unit_plan: UnitPlan, *, settings: Settings, output: Path, base_identity: tuple[str, ...]
) -> Path:
    """Build from locally configured reference documents into a workspace path."""
    if settings.audit_base_document is None or settings.audit_measurement_prototype is None:
        raise ValueError("audit base and measurement prototype must be configured")
    return build_base(
        unit_plan,
        base_document=settings.audit_base_document,
        measurement_prototype=settings.audit_measurement_prototype,
        output=output,
        base_identity=base_identity,
    )
