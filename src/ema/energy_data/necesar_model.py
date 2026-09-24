"""Located values produced by the Necesar info reader."""

from __future__ import annotations

from dataclasses import dataclass, field

from ema.energy_data.carriers import Carrier
from ema.energy_data.source import Located, ReaderIssue


@dataclass
class YearValues:
    months: tuple[Located | None, ...]
    total: Located | None
    tep_months: tuple[Located | None, ...] = (None,) * 12
    tep_total: Located | None = None


@dataclass
class Consumption:
    label: Located
    years: dict[int, YearValues] = field(default_factory=dict[int, YearValues])
    installed_power: list[Located] = field(default_factory=list[Located])


@dataclass
class Production:
    name: Located
    unit: Located
    years: dict[int, YearValues] = field(default_factory=dict[int, YearValues])


@dataclass
class GenericRow:
    values: dict[str, Located]
    continuation: list[Located] = field(default_factory=list[Located])


@dataclass
class GenericTable:
    sheet: str
    rows: list[GenericRow]


@dataclass
class NecesarInfo:
    carriers: dict[Carrier, Consumption] = field(default_factory=dict[Carrier, Consumption])
    water: dict[Carrier, Consumption] = field(default_factory=dict[Carrier, Consumption])
    production: list[Production] = field(default_factory=list[Production])
    economics: dict[str, dict[int, Located]] = field(default_factory=dict[str, dict[int, Located]])
    employees: dict[int, Located] = field(default_factory=dict[int, Located])
    other_consumption: list[dict[str, Located]] = field(default_factory=list[dict[str, Located]])
    tables: dict[str, GenericTable] = field(default_factory=dict[str, GenericTable])
    issues: list[ReaderIssue] = field(default_factory=list[ReaderIssue])
