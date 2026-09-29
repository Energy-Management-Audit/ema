"""Review labels and presentation for the section catalogue's fact vocabulary."""

from ema.audit.catalogue_types import AuditFact
from ema.audit.reading_labels import READING_LABELS
from ema.core.review.models import FieldSpec, ValueType

CEDILLA = str.maketrans("șțȘȚ", "şţŞŢ")
FACT_LABELS: dict[str, str] = {
    AuditFact.COMPANY_NAME: "Denumirea societăţii",
    AuditFact.CUI: "CUI",
    AuditFact.REGISTRATION: "Registrul Comerţului",
    AuditFact.ADDRESS: "Adresa",
    AuditFact.PHONE: "Telefon",
    AuditFact.WEBSITE: "Website",
    AuditFact.CAEN_CODE: "Cod CAEN",
    AuditFact.CAEN_DESCRIPTION: "Sector de activitate",
    AuditFact.OWNERSHIP_STATE: "Capital de stat (%)",
    AuditFact.OWNERSHIP_PRIVATE: "Capital privat (%)",
    AuditFact.EMPLOYEES: "Angajaţi",
    AuditFact.TEP_CLASS: "Pragul 1000 tep",
    AuditFact.ENERGY_MANAGER: "Manager energetic",
    AuditFact.BUSINESS_ACTIVITY: "Activitatea societăţii",
    AuditFact.LOCATION: "Localizarea societăţii",
    AuditFact.HISTORY: "Istoricul societăţii",
    AuditFact.PROCESS_SECTIONS: "Fluxul tehnologic",
    AuditFact.EQUIPMENT: "Echipamente",
    AuditFact.WATER_SUPPLY: "Alimentarea cu apă",
    AuditFact.ELECTRICITY_SUPPLY: "Alimentarea cu energie electrică",
    AuditFact.GAS_SUPPLY: "Alimentarea cu gaze naturale",
    AuditFact.FUEL_SUPPLY: "Alimentarea cu carburanţi",
    AuditFact.COMPRESSED_AIR: "Aer comprimat",
    AuditFact.HVAC: "Climatizare",
    AuditFact.LIGHTING: "Iluminat",
    AuditFact.FLEET: "Parc auto",
    AuditFact.METERING: "Contorizare",
    AuditFact.AUTOMATION: "Automatizare",
    AuditFact.PRODUCTION: "Producţie",
}
IDENTIFIERS = frozenset(
    {"audit.cui", "audit.caen_code", "audit.registrul_comertului", "audit.phone"}
)
THERMAL_LABELS = {
    "component": "Componentă",
    "spot": "Temperatura în punctul măsurat",
    "max": "Temperatura maximă",
    "min": "Temperatura minimă",
}
MEASURE_LABELS = {
    "title": "denumire",
    "effect": "efect",
    "carrier": "tip de energie",
    "saving_amount": "economie",
    "saving_tep": "economie (tep)",
    "investment_thousand_lei": "investiţie (mii lei)",
    "cost_saving_thousand_lei": "economie financiară (mii lei/an)",
    "cost_note": "observaţii",
    "payback": "durata de recuperare (ani)",
    "description": "descriere",
    "co2_t": "reducerea emisiilor (t CO₂)",
    "payback_years": "durata de recuperare (ani)",
}
ECONOMIC_LABELS = {
    "production_value_lei": "Valoarea totală a producţiei",
    "operating_revenue_lei": "Venituri totale din exploatare",
    "operating_costs_lei": "Cheltuieli de exploatare",
    "energy_cost_share": "Ponderea energiei în costuri",
    "electricity_costs_lei": "Cheltuieli cu energia electrică",
    "heat_costs_lei": "Cheltuieli cu energia termică",
    "gas_costs_lei": "Cheltuieli cu gazele naturale",
    "diesel_costs_lei": "Cheltuieli cu motorina",
    "petrol_costs_lei": "Cheltuieli cu benzina",
    "lpg_costs_lei": "Cheltuieli cu GPL",
}
CARRIER_LABELS = {
    "electricity_grid": "Energie electrică din reţea",
    "electricity_pv": "Energie electrică fotovoltaică",
    "natural_gas": "Gaze naturale",
    "diesel": "Motorină",
    "petrol": "Benzină",
    "lpg": "GPL",
    "fuel_oil": "Păcură",
    "clu": "CLU",
    "coal": "Cărbune",
    "coke": "Cocs",
    "wood": "Lemn",
    "biomass": "Biomasă",
    "sunflower_husks": "Coji de floarea soarelui",
    "biogas": "Biogaz",
    "ctl": "CTL",
    "purchased_heat": "Energie termică achiziţionată",
    "water_potable": "Apă potabilă",
    "water_industrial": "Apă industrială",
    "water_storm": "Apă pluvială",
}


def field_label(  # noqa: C901, PLR0911
    key: str, source_label: str | None = None
) -> str:
    if key in FACT_LABELS:
        return FACT_LABELS[key]
    parts = key.split(".")
    if key.startswith("audit.economics."):
        return f"{ECONOMIC_LABELS[parts[2]]} {parts[3]}"
    if key.startswith("audit.employees."):
        return f"Angajaţi {parts[-1]}"
    if key == "audit_measure.count":
        return "Numărul măsurilor"
    if key.startswith("audit_measure.") and len(parts) == 3:
        return f"Măsura {parts[1]} – {MEASURE_LABELS[parts[2]]}"
    if key.startswith("meter.") and len(parts) >= 5:
        return READING_LABELS.get((parts[-2], parts[-1]), "Valoarea măsurată").translate(CEDILLA)
    if key.startswith("thermal."):
        return THERMAL_LABELS[parts[-1]]
    if parts[0] in {"carrier", "carrier_tep"}:
        label = CARRIER_LABELS[parts[1]] + (" (tep)" if parts[0] == "carrier_tep" else "")
        return f"{label} – {' / '.join(parts[2:])}"
    if parts[0] in {"turnover", "energy_costs", "production"}:
        label = {
            "turnover": "Cifra de afaceri",
            "energy_costs": "Cheltuieli cu energia",
            "production": "Producţie",
        }[parts[0]]
        return f"{label} – {' / '.join(part.replace('_', ' ') for part in parts[1:])}"
    if source_label:
        return source_label.translate(CEDILLA)
    # Questionnaire table columns are already Romanian; retain their wording.
    return parts[-1].replace("_", " ").capitalize().translate(CEDILLA)


def fact_spec(
    key: str,
    value_type: ValueType,
    *,
    chapter: str = "",
    unit: str | None = None,
    decimals: int | None = None,
    source_label: str | None = None,
) -> FieldSpec:
    count = key.startswith("audit.employees")
    return FieldSpec(
        key=key,
        label=field_label(key, source_label),
        value_type="text" if key in IDENTIFIERS else value_type,
        chapter=chapter,
        unit=unit,
        decimals=0 if count or value_type == "year" else (2 if decimals is None else decimals),
        grouping=not (value_type == "year" or key in IDENTIFIERS),
    )
