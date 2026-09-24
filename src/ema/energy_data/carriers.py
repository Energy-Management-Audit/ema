"""Closed energy and water carrier vocabulary with conservative label matching."""

from __future__ import annotations

import re
import unicodedata
from enum import StrEnum


class Carrier(StrEnum):
    electricity_grid = "electricity_grid"
    electricity_pv = "electricity_pv"
    natural_gas = "natural_gas"
    diesel = "diesel"
    petrol = "petrol"
    lpg = "lpg"
    fuel_oil = "fuel_oil"
    clu = "clu"
    coal = "coal"
    coke = "coke"
    wood = "wood"
    biomass = "biomass"
    sunflower_husks = "sunflower_husks"
    biogas = "biogas"
    ctl = "ctl"
    purchased_heat = "purchased_heat"
    water_potable = "water_potable"
    water_industrial = "water_industrial"
    water_storm = "water_storm"


WATER_CARRIERS = frozenset({Carrier.water_potable, Carrier.water_industrial, Carrier.water_storm})


def _normalize(label: str) -> str:
    decomposed = unicodedata.normalize("NFKD", label.casefold())
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", plain))


_ALIASES: dict[Carrier, tuple[str, ...]] = {
    Carrier.electricity_grid: (
        "energie electrica",
        "consum energie electrica",
        "electricitate",
        "energie electrica din retea",
        "energie electrica achizitionata",
        "energie electrică [tep]",
        "electricitate [mwh]",
        "consum electric",
        "consum energie electrica din SEN",
        "consum energie electrica din SEN (Sistem Energetic National - facturi)",
    ),
    Carrier.electricity_pv: (
        "energie electrica fotovoltaica",
        "consum electrica fotovoltaic",
        "energie electrică din surse regenerabile",
        "energ electrică din surse recuperabile",
        "energie electrica surse recuperabile",
        "electricitate fotovoltaica",
        "fotovoltaic",
        "consum energie electrica din parcul fotovoltaic propriu",
        "consum energie electrica din fotovoltaic propriu",
        "consum energie electrica FOTOVOLTAI",
    ),
    Carrier.natural_gas: (
        "gaz",
        "gaze",
        "gaze naturale",
        "gaz natural",
        "consum gaz",
        "consum gaze naturale",
        "gaze [tep]",
        "gaz [tep]",
        "consum gaz natural",
    ),
    Carrier.diesel: ("motorina", "motorină", "consum motorina", "motorina [t]", "motorina [tep]"),
    Carrier.petrol: (
        "benzina",
        "benzină",
        "consum benzina",
        "consum bezina",
        "benzina [t]",
        "benzina [tep]",
    ),
    Carrier.lpg: (
        "gpl",
        "alti comb gpl",
        "alți comb – gpl",
        "alti combustibili - gpl",
        "gaz petrolier lichefiat",
        "consum GPL",
    ),
    Carrier.fuel_oil: ("pacura", "păcură", "combustibil lichid greu"),
    Carrier.clu: ("clu", "combustibil lichid usor", "combustibil lichid ușor"),
    Carrier.coal: ("carbune", "cărbune", "carbune slab", "lignit"),
    Carrier.coke: ("cocs", "coke", "carbune (cocs)"),
    Carrier.wood: ("lemn", "lemne de foc", "biomasa lemnoasa"),
    Carrier.biomass: ("biomasa", "biomasă"),
    Carrier.sunflower_husks: (
        "coji floarea soarelui",
        "coji de floarea soarelui",
        "consum coji floarea soarelui",
    ),
    Carrier.biogas: ("biogaz", "biogas"),
    Carrier.ctl: ("ctl", "combustibil termic lichid"),
    Carrier.purchased_heat: (
        "energie termica terti",
        "energie termică terți",
        "energie termica de la terti",
        "consum energie termica terti",
        "consum energie termica de la terti",
    ),
    Carrier.water_potable: (
        "apa potabila",
        "apă potabilă",
        "consum apa potabila",
        "consum apa potabilla",
        "consum apa potabila - m3",
    ),
    Carrier.water_industrial: (
        "apa industriala",
        "apă industrială",
        "consum apa industriala",
        "consum apa industriala - m3",
    ),
    Carrier.water_storm: (
        "apa pluviala",
        "apă pluvială",
        "apa meteorica",
        "apă meteorică",
        "consum apa meteorica, etc",
    ),
}

ALIASES = {carrier: tuple(sorted(set(labels))) for carrier, labels in _ALIASES.items()}
_LOOKUP = {_normalize(label): carrier for carrier, labels in ALIASES.items() for label in labels}


def carrier_for(label: str) -> Carrier | None:
    """Return a carrier for a known complete label, never by a fuzzy guess."""
    key = _normalize(label)
    if key in _LOOKUP:
        return _LOOKUP[key]
    return _LOOKUP.get(re.sub(r"\s+(?:mwh|kwh|gcal|tep|t|tone|m3|nm3)$", "", key))
