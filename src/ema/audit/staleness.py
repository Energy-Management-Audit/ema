"""Compare a drafted section's recorded inputs with current audit inputs."""

from __future__ import annotations

import sqlite3

from ema.audit.applicability import fact_fields
from ema.audit.catalogue import AuditFact, Condition, Section
from ema.core.review.models import Field
from ema.core.review.section_transition import SectionState, Status
from ema.core.workspace import Workspace


def _condition_inputs(condition: Condition) -> tuple[set[str], set[str]]:
    facts: set[str] = set()
    materials: set[str] = set()
    if condition.op == "fact":
        facts.add(condition.key)
    elif condition.op == "material":
        materials.add(condition.key)
    for child in condition.children:
        child_facts, child_materials = _condition_inputs(child)
        facts.update(child_facts)
        materials.update(child_materials)
    return facts, materials


def snapshot_inputs(
    section: Section,
    fingerprint: tuple[str, ...],
    facts: dict[str, Field],
    materials: dict[str, tuple[bool, str]],
) -> tuple[dict[str, int | None], dict[str, tuple[bool, str] | None]]:
    fact_keys, material_keys = _condition_inputs(section.applies_when)
    material_keys.update(kind.value for kind in section.awaits)
    for ref in section.facts:
        if isinstance(ref, AuditFact):
            fact_keys.add(ref.value)
        else:
            fact_keys.update(field.key for field in fact_fields(ref, facts))
    fact_keys.update(item.removeprefix("fact:") for item in fingerprint if item.startswith("fact:"))
    material_keys.update(
        item.removeprefix("material:") for item in fingerprint if item.startswith("material:")
    )
    return (
        {key: facts[key].revision if key in facts else None for key in sorted(fact_keys)},
        {key: materials.get(key) for key in sorted(material_keys)},
    )


def current_inputs(
    db: sqlite3.Connection, job: str
) -> tuple[dict[str, Field], dict[str, tuple[bool, str]]]:
    facts = {
        str(row["key"]): Field.model_validate_json(row["data"])
        for row in db.execute("SELECT key,data FROM fields WHERE job_id=?", (job,))
    }
    materials = {
        str(row["kind"]): (bool(row["present"]), str(row["source"]))
        for row in db.execute(
            "SELECT kind,present,source FROM audit_materials WHERE job_id=?", (job,)
        )
    }
    return facts, materials


def capture_inputs(
    ws: Workspace, job: str, section: Section, fingerprint: tuple[str, ...]
) -> tuple[dict[str, int | None], dict[str, tuple[bool, str] | None]]:
    with ws.connect() as db:
        return snapshot_inputs(section, fingerprint, *current_inputs(db, job))


def base_changed(state: SectionState, current: str) -> str | None:
    """The `base:` entry of a confirmed or drafted section written from another base."""
    if state.status not in (Status.DRAFTED, Status.DONE) or state.stale:
        return None
    return next(
        (
            item
            for item in state.fingerprint
            if item.startswith("base:") and item != f"base:{current}"
        ),
        None,
    )
