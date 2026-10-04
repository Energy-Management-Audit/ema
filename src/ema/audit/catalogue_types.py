"""the auditor's audit structure and the inputs that make each section applicable."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from ema.energy_data.carriers import Carrier


class MaterialKind(StrEnum):
    METER = "meter_photos"
    THERMAL = "thermal_images"
    VISIT = "visit_photos"
    MAP = "map"
    MEASURES = "measures_form"


class AuditFact(StrEnum):
    COMPANY_NAME = "audit.company_name"
    CUI = "audit.cui"
    REGISTRATION = "audit.registrul_comertului"
    ADDRESS = "audit.address"
    PHONE = "audit.phone"
    WEBSITE = "audit.website"
    CAEN_CODE = "audit.caen_code"
    CAEN_DESCRIPTION = "audit.caen_description"
    OWNERSHIP_STATE = "audit.ownership_state"
    OWNERSHIP_PRIVATE = "audit.ownership_private"
    EMPLOYEES = "audit.employees"
    TEP_CLASS = "audit.tep_class"
    ENERGY_MANAGER = "audit.energy_manager"
    BUSINESS_ACTIVITY = "audit.business_activity"
    LOCATION = "audit.location"
    HISTORY = "audit.history"
    PROCESS_SECTIONS = "audit.process_sections"
    EQUIPMENT = "audit.equipment"
    WATER_SUPPLY = "audit.water_supply"
    ELECTRICITY_SUPPLY = "audit.electricity_supply"
    GAS_SUPPLY = "audit.gas_supply"
    FUEL_SUPPLY = "audit.fuel_supply"
    COMPRESSED_AIR = "audit.compressed_air"
    HVAC = "audit.hvac"
    LIGHTING = "audit.lighting"
    FLEET = "audit.fleet"
    METERING = "audit.metering"
    AUTOMATION = "audit.automation"
    PRODUCTION = "audit.production"
    WORK_REGIME = "audit.work_regime"
    HEATING = "audit.heating"
    PV_POWER = "audit.pv.power"
    PV_YEAR = "audit.pv.year"


# Narrative facts are whole verbatim source passages. A description in several places, as the
# per-stage process flows, keeps its first passage under the key and each later one under
# `<key>.<n>`, so a draft writes one paragraph per passage.
PASSAGE_FACTS = frozenset(
    {
        AuditFact.HISTORY,
        AuditFact.BUSINESS_ACTIVITY,
        AuditFact.PROCESS_SECTIONS,
        AuditFact.WATER_SUPPLY,
        AuditFact.ELECTRICITY_SUPPLY,
        AuditFact.GAS_SUPPLY,
        AuditFact.COMPRESSED_AIR,
        AuditFact.HVAC,
        AuditFact.LIGHTING,
        AuditFact.HEATING,
        AuditFact.EQUIPMENT,
        AuditFact.METERING,
    }
)
MAX_PASSAGES = 6
# The process flow keeps a passage per stage of every process unit (D3).
MAX_PROCESS_PASSAGES = 12
# A 3.1.x unit's heading, numbered from 1 in unit order: audit.process_unit.<i>.name.
PROCESS_UNIT = "audit.process_unit."
_UNIT_NAME = re.compile(rf"^{re.escape(PROCESS_UNIT)}([1-9]\d*)\.name$")


def max_passages(key: str) -> int:
    return MAX_PROCESS_PASSAGES if key == AuditFact.PROCESS_SECTIONS else MAX_PASSAGES


def passage_key(key: str, number: int) -> str:
    return key if number == 1 else f"{key}.{number}"


def process_unit_name(number: int) -> str:
    return f"{PROCESS_UNIT}{number}.name"


def process_unit_number(key: str) -> int | None:
    """The unit a name key belongs to: `audit.process_unit.2.name` is unit 2."""
    match = _UNIT_NAME.match(key)
    return int(match.group(1)) if match else None


def fact_key(key: str) -> str:
    """The catalogue fact a stored key belongs to: `audit.history.2` is `audit.history`."""
    base, _, number = key.rpartition(".")
    numbered = base in PASSAGE_FACTS and number.isdigit() and 2 <= int(number) <= max_passages(base)
    return base if numbered else key


@dataclass(frozen=True)
class CarrierPattern:
    carriers: tuple[Carrier, ...] = ()


@dataclass(frozen=True)
class PrefixPattern:
    prefix: str


FactRef = AuditFact | CarrierPattern | PrefixPattern


def carrier_fact(*carriers: Carrier) -> CarrierPattern:
    return CarrierPattern(carriers)


SectionKind = Literal["fixed", "data", "narrative", "data_blocks", "measurements", "calc"]
Source = Literal[
    "template",
    "clients",
    "anexa",
    "questionnaire",
    "online",
    "dossier",
    "visit",
    "consumption_analysis",
    "measurements",
    "auditor",
    "calculation",
]


@dataclass(frozen=True)
class Condition:
    op: Literal["always", "material", "fact", "carrier", "any", "all"]
    key: str = ""
    children: tuple[Condition, ...] = ()
    carriers: tuple[Carrier, ...] = ()


def material(kind: MaterialKind) -> Condition:
    return Condition("material", kind)


def fact(key: AuditFact) -> Condition:
    return Condition("fact", key.value)


def carrier_condition(*carriers: Carrier) -> Condition:
    return Condition("carrier", carriers=carriers)


ALWAYS = Condition("always")


@dataclass(frozen=True)
class PrototypeRef:
    audit: str
    heading_path: tuple[str, ...]


@dataclass(frozen=True)
class Section:
    id: str
    chapter: int
    title: str
    aliases: tuple[str, ...]
    parent: str | None
    kind: SectionKind
    sources: tuple[Source, ...]
    applies_when: Condition
    prototype: PrototypeRef
    facts: tuple[FactRef, ...] = ()
    templates: tuple[str, ...] = ()
    awaits: tuple[MaterialKind, ...] = ()
    has_intro_content: bool = False


def section(  # noqa: PLR0913
    id: str,
    chapter: int,
    title: str,
    parent: str | None,
    kind: SectionKind,
    sources: tuple[Source, ...],
    *,
    aliases: tuple[str, ...] = (),
    when: Condition = ALWAYS,
    prototype: str = "audit-01",
    facts: tuple[FactRef, ...] = (),
    templates: tuple[str, ...] = (),
    has_intro_content: bool = False,
) -> Section:
    title = title.translate(str.maketrans("şţŞŢ", "șțȘȚ"))
    return Section(
        id,
        chapter,
        title,
        aliases,
        parent,
        kind,
        sources,
        when,
        PrototypeRef(prototype, (title,)),
        facts,
        templates,
        has_intro_content=has_intro_content,
    )
