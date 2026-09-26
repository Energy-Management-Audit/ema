"""the auditor's audit structure and the inputs that make each section applicable."""

from __future__ import annotations

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
    prototype: str = "AUDIT-01",
    facts: tuple[FactRef, ...] = (),
    templates: tuple[str, ...] = (),
) -> Section:
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
    )
