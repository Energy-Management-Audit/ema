"""Frozen union of section prototypes and one audit fact vocabulary."""

from dataclasses import replace

from ema.audit.catalogue_analysis import ANALYSIS
from ema.audit.catalogue_general import GENERAL
from ema.audit.catalogue_types import (
    AuditFact,
    CarrierPattern,
    Condition,
    FactRef,
    MaterialKind,
    PrefixPattern,
    PrototypeRef,
    Section,
    SectionKind,
    Source,
    carrier_condition,
    carrier_fact,
    fact,
    material,
)
from ema.energy_data.carriers import WATER_CARRIERS, Carrier

_FUELS = (Carrier.diesel, Carrier.petrol, Carrier.lpg, Carrier.fuel_oil, Carrier.clu)
_ELECTRIC = (Carrier.electricity_grid,)
_PV = (Carrier.electricity_pv,)
_WATER = tuple(sorted(WATER_CARRIERS))
_FACTS: dict[str, tuple[FactRef, ...]] = {
    "ch2.date_generale": (
        AuditFact.COMPANY_NAME,
        AuditFact.CUI,
        AuditFact.REGISTRATION,
        AuditFact.ADDRESS,
        AuditFact.PHONE,
        AuditFact.WEBSITE,
        AuditFact.CAEN_CODE,
        AuditFact.CAEN_DESCRIPTION,
        AuditFact.OWNERSHIP_STATE,
        AuditFact.OWNERSHIP_PRIVATE,
        AuditFact.EMPLOYEES,
        AuditFact.TEP_CLASS,
    ),
    "ch2.manager": (AuditFact.ENERGY_MANAGER,),
    "ch2.activitate": (AuditFact.BUSINESS_ACTIVITY,),
    "ch2.localizare": (AuditFact.LOCATION,),
    "ch2.istorie": (AuditFact.HISTORY,),
    "ch3.flux": (AuditFact.PROCESS_SECTIONS, AuditFact.EQUIPMENT),
    "ch3.process": (AuditFact.PROCESS_SECTIONS, AuditFact.EQUIPMENT),
    "ch3.utilitati": (
        AuditFact.WATER_SUPPLY,
        AuditFact.ELECTRICITY_SUPPLY,
        AuditFact.GAS_SUPPLY,
        AuditFact.FUEL_SUPPLY,
    ),
    "ch3.apa": (AuditFact.WATER_SUPPLY,),
    "ch3.electricitate": (AuditFact.ELECTRICITY_SUPPLY,),
    "ch3.gaz": (AuditFact.GAS_SUPPLY,),
    "ch3.carburant": (AuditFact.FUEL_SUPPLY,),
    "ch3.aer_comprimat": (AuditFact.COMPRESSED_AIR,),
    "ch3.climatizare": (AuditFact.HVAC,),
    "ch3.iluminat": (AuditFact.LIGHTING,),
    "ch3.parc_auto": (AuditFact.FLEET,),
    "ch3.contorizare": (AuditFact.METERING,),
    "ch3.automatizare": (AuditFact.AUTOMATION,),
    "ch3.consumatori": (AuditFact.EQUIPMENT,),
    "ch3.equipment": (AuditFact.EQUIPMENT,),
    "ch4.productie": (AuditFact.PRODUCTION,),
    "ch4.consum": (carrier_fact(),),
    "ch4.electricitate": (carrier_fact(*_ELECTRIC),),
    "ch4.electricitate_pv": (carrier_fact(*_PV),),
    "ch4.gaz": (carrier_fact(Carrier.natural_gas),),
    "ch4.carburant": (carrier_fact(*_FUELS),),
    "ch4.apa": (carrier_fact(*_WATER),),
    "ch4.echivalent": (carrier_fact(),),
    "ch4.echiv_electric": (carrier_fact(*_ELECTRIC),),
    "ch4.echiv_pv": (carrier_fact(*_PV),),
    "ch4.echiv_gaz": (carrier_fact(Carrier.natural_gas),),
    "ch4.echiv_carburant": (carrier_fact(*_FUELS),),
    "ch4.echiv_total": (carrier_fact(),),
    "ch4.specific_electric": (carrier_fact(*_ELECTRIC),),
    "ch4.specific_pv": (carrier_fact(*_PV),),
    "ch4.specific_gaz": (carrier_fact(Carrier.natural_gas),),
    "ch4.specific_carburant": (carrier_fact(*_FUELS),),
    "ch4.specific_total": (carrier_fact(),),
    "ch4.specific_apa": (carrier_fact(*_WATER),),
    "ch5": (PrefixPattern("visit."),),
    "ch5.electric": (PrefixPattern("visit."),),
    "ch5.electric_fisa": (PrefixPattern("meter."), PrefixPattern("narrative.ch5.")),
    "ch5.electric_rezultate": (PrefixPattern("meter."), PrefixPattern("narrative.ch5.")),
    "ch5.electric_concluzii": (PrefixPattern("meter."), PrefixPattern("narrative.ch5.")),
    "ch5.termic": (PrefixPattern("visit."),),
    "ch5.termic_fisa": (PrefixPattern("thermal."), PrefixPattern("narrative.ch5.termic")),
    "ch5.termic_rezultate": (PrefixPattern("thermal."), PrefixPattern("narrative.ch5.termic")),
    "ch6.specifice": (PrefixPattern("audit_measure."), PrefixPattern("narrative.ch6.")),
    "ch6.measure": (PrefixPattern("audit_measure."), PrefixPattern("narrative.ch6.")),
    "ch6.sinteza": (PrefixPattern("audit_measure."), PrefixPattern("narrative.ch6.")),
}
_CONDITIONS: dict[str, Condition] = {
    "ch2.manager": fact(AuditFact.ENERGY_MANAGER),
    "ch2.activitate": fact(AuditFact.BUSINESS_ACTIVITY),
    "ch3.process": fact(AuditFact.PROCESS_SECTIONS),
    "ch3.apa": fact(AuditFact.WATER_SUPPLY),
    "ch3.electricitate": fact(AuditFact.ELECTRICITY_SUPPLY),
    "ch3.gaz": fact(AuditFact.GAS_SUPPLY),
    "ch3.carburant": fact(AuditFact.FUEL_SUPPLY),
    "ch3.aer_comprimat": fact(AuditFact.COMPRESSED_AIR),
    "ch3.climatizare": fact(AuditFact.HVAC),
    "ch3.iluminat": fact(AuditFact.LIGHTING),
    "ch3.parc_auto": fact(AuditFact.FLEET),
    "ch3.contorizare": fact(AuditFact.METERING),
    "ch3.automatizare": fact(AuditFact.AUTOMATION),
    "ch3.consumatori": fact(AuditFact.EQUIPMENT),
    "ch4.productie": fact(AuditFact.PRODUCTION),
    "ch4.electricitate": carrier_condition(*_ELECTRIC),
    "ch4.electricitate_pv": carrier_condition(*_PV),
    "ch4.gaz": carrier_condition(Carrier.natural_gas),
    "ch4.carburant": carrier_condition(*_FUELS),
    "ch4.apa": carrier_condition(*_WATER),
    "ch4.echiv_electric": carrier_condition(*_ELECTRIC),
    "ch4.echiv_pv": carrier_condition(*_PV),
    "ch4.echiv_gaz": carrier_condition(Carrier.natural_gas),
    "ch4.echiv_carburant": carrier_condition(*_FUELS),
    "ch4.specific_electric": carrier_condition(*_ELECTRIC),
    "ch4.specific_pv": carrier_condition(*_PV),
    "ch4.specific_gaz": carrier_condition(Carrier.natural_gas),
    "ch4.specific_carburant": carrier_condition(*_FUELS),
    "ch4.specific_apa": carrier_condition(*_WATER),
    "ch6.specifice": material(MaterialKind.MEASURES),
    "ch6.measure": material(MaterialKind.MEASURES),
    "ch6.sinteza": material(MaterialKind.MEASURES),
}
_AWAITS: dict[str, tuple[MaterialKind, ...]] = {
    "ch2.localizare": (MaterialKind.MAP,),
    "ch3.flux": (MaterialKind.VISIT,),
    "ch5": (MaterialKind.METER, MaterialKind.THERMAL),
    "ch5.electric": (MaterialKind.METER,),
    "ch5.electric_fisa": (MaterialKind.METER,),
    "ch5.electric_rezultate": (MaterialKind.METER,),
    "ch5.electric_concluzii": (MaterialKind.METER,),
    "ch5.termic": (MaterialKind.THERMAL,),
    "ch5.termic_fisa": (MaterialKind.THERMAL,),
    "ch5.termic_rezultate": (MaterialKind.THERMAL,),
    "ch6.specifice": (MaterialKind.MEASURES,),
    "ch6.measure": (MaterialKind.MEASURES,),
    "ch6.sinteza": (MaterialKind.MEASURES,),
}

_ENTRIES: tuple[Section, ...] = (*GENERAL, *ANALYSIS)
_ROOTS = {section.chapter: section.title for section in _ENTRIES if section.parent is None}
CATALOGUE: tuple[Section, ...] = tuple(
    replace(
        section,
        facts=_FACTS.get(section.id, section.facts),
        applies_when=_CONDITIONS.get(section.id, section.applies_when),
        awaits=_AWAITS.get(section.id, section.awaits),
        prototype=PrototypeRef(
            section.prototype.audit,
            (section.title,)
            if section.parent is None
            else (_ROOTS[section.chapter], section.title),
        ),
    )
    for section in _ENTRIES
)

NOT_SECTIONS: dict[str, str] = {
    "cuprins": "front matter",
    "abrevieri": "front matter",
}

__all__ = [
    "CATALOGUE",
    "NOT_SECTIONS",
    "AuditFact",
    "CarrierPattern",
    "Condition",
    "MaterialKind",
    "PrototypeRef",
    "Section",
    "SectionKind",
    "Source",
    "fact",
    "material",
]
