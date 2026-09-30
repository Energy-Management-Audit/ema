"""Replay-only entry point for a synthetic dossier's per-section Fill stage."""

from __future__ import annotations

PROMPT_VERSION = "audit-fill-v1"
INSTRUCTIONS = (
    "Read the dossier and dataset for this section. Record facts only with verbatim "
    "source quotes or an exact dataset field. Mark missing facts, defer unavailable "
    "material, and propose n/a only when the catalogue trigger is absent. "
    "Never infer a number that is not in a source."
)
