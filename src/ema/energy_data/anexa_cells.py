"""Value and cell-location types shared by Anexa 2–3 sections."""

from __future__ import annotations

from dataclasses import dataclass, field

from ema.energy_data.source import Located, ReaderIssue


@dataclass(frozen=True)
class Measure:
    kind: str
    description: Located
    commissioning_year: Located | None
    values: dict[str, Located]
    location: Located | None = None


@dataclass
class AnexaData:
    """Raw form values; carrier keys use the canonical vocabulary and retain source units."""

    year: Located | None = None
    identity: dict[str, Located] = field(default_factory=dict[str, Located])
    name_origin: str | None = None
    annual: dict[str, Located] = field(default_factory=dict[str, Located])
    monthly_total_tep: Located | None = None
    monthly: dict[str, dict[int, Located]] = field(default_factory=dict[str, dict[int, Located]])
    monthly_unresolved: dict[str, dict[int, Located]] = field(
        default_factory=dict[str, dict[int, Located]]
    )
    existing_measures: list[Measure] = field(default_factory=list[Measure])
    planned_measures: list[Measure] = field(default_factory=list[Measure])
    audit: dict[str, Located] = field(default_factory=dict[str, Located])
    issues: list[ReaderIssue] = field(default_factory=list[ReaderIssue])
