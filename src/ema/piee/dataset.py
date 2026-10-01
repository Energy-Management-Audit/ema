"""Source-ordered PIEE inputs and the annual filing cross-check."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from ema.core.errors import EmaError
from ema.energy_data.anexa import parse_anexa
from ema.energy_data.anexa_cells import AnexaData
from ema.energy_data.calc import co2, tep
from ema.energy_data.carriers import FAMILY_PARENT, Carrier, counts_in_total
from ema.energy_data.factors import FACTORS_2026, FactorTable
from ema.energy_data.model import CarrierSeries, Derived, EnergyDataset, Reading
from ema.energy_data.necesar import parse_necesar_info, to_dataset
from ema.energy_data.necesar_model import NecesarInfo
from ema.energy_data.prelucrare import import_prelucrare
from ema.energy_data.prelucrare_factors import factors_for_output
from ema.energy_data.prelucrare_merge import merge_prelucrare
from ema.energy_data.prelucrare_types import PrelucrareData
from ema.energy_data.reconcile import reconcile
from ema.energy_data.source import Located
from ema.piee.annual_check import AnnualCheck, annual_check
from ema.piee.prelucrare_compat import existing_piee_readings
from ema.piee.units import (
    Conversion,
    delivered_pie_representation,
    delivered_separate_pv_figures,
    presentation_dataset,
)


@dataclass(frozen=True)
class SourceDisagreement:
    key: str
    chosen: Reading
    alternative: Reading
    chosen_source: str
    alternative_source: str
    chosen_location: Located | None = None
    alternative_location: Located | None = None


@dataclass(frozen=True)
class PieeData:
    year: int
    anexa: AnexaData
    necesar: NecesarInfo
    prelucrare: PrelucrareData | None
    dataset: EnergyDataset
    factors: FactorTable
    disagreements: tuple[SourceDisagreement, ...]
    annual_check: AnnualCheck
    necesar_status: str = "received"
    production_conversion: Conversion | None = None
    pie_representation: str = "normalized"
    pie_representation_source: str = "base"
    separate_pv_figures: bool = True


def _anexa_series(anexa: AnexaData, year: int) -> dict[Carrier, tuple[CarrierSeries, Located]]:
    result: dict[Carrier, tuple[CarrierSeries, Located]] = {}
    for carrier in Carrier:
        key = f"{carrier.value}_raw"
        value = anexa.annual.get(key)
        if value is None or not isinstance(value.value, int | float) or not value.unit:
            continue
        result[carrier] = (CarrierSeries(annual=Reading(float(value.value), value.unit)), value)
    for carrier, key in (
        (Carrier.electricity_grid, "electricity_grid_mwh"),
        (Carrier.electricity_pv, "electricity_pv_mwh"),
        (Carrier.purchased_heat, "purchased_heat_gcal"),
    ):
        value = anexa.annual.get(key)
        if carrier in result or value is None or not isinstance(value.value, int | float):
            continue
        unit = {
            "electricity_grid_mwh": "MWh",
            "electricity_pv_mwh": "MWh",
            "purchased_heat_gcal": "Gcal",
        }[key]
        result[carrier] = (CarrierSeries(annual=Reading(float(value.value), unit)), value)
    return result


def _merge_anexa(
    dataset: EnergyDataset,
    anexa: AnexaData,
    year: int,
    necesar_locations: dict[str, Located],
    family_aggregates: frozenset[Carrier],
) -> tuple[EnergyDataset, list[SourceDisagreement], dict[str, Located]]:
    carriers = {carrier: dict(series) for carrier, series in dataset.carriers.items()}
    disagreements: list[SourceDisagreement] = []
    selected: dict[str, Located] = {}
    for carrier, (candidate, located) in _anexa_series(anexa, year).items():
        if carrier in family_aggregates:
            continue
        if candidate.annual is None:
            raise ValueError("Anexa annual candidate has no annual value")
        key = f"carrier.{carrier.value}.{year}"
        current = carriers.get(carrier, {}).get(year)
        if current is None:
            if candidate.annual.value == 0:
                continue
            carriers.setdefault(carrier, {})[year] = candidate
            selected[key] = located
        elif current.annual is None:
            carriers[carrier][year] = CarrierSeries(current.months, candidate.annual)
            selected[key] = located
        elif current.annual != candidate.annual:
            disagreements.append(
                SourceDisagreement(
                    key,
                    current.annual,
                    candidate.annual,
                    "necesar",
                    "anexa",
                    necesar_locations.get(key),
                    located,
                )
            )
    years = tuple(sorted(set(dataset.years) | {year}))
    return (
        EnergyDataset(
            years,
            carriers,
            dataset.production,
            dataset.production_unit,
            dataset.turnover_lei,
            dataset.energy_costs_lei,
            dataset.filed_indicators,
            dataset.energy_inventory_complete,
        ),
        disagreements,
        selected,
    )


def _family_evidence(
    anexa: AnexaData, year: int, prelucrare: PrelucrareData | None
) -> tuple[frozenset[Carrier], list[SourceDisagreement]]:
    if prelucrare is None:
        return frozenset(), []
    covered: set[Carrier] = set()
    conflicts: list[SourceDisagreement] = []
    for subtype, parent in FAMILY_PARENT.items():
        if year not in prelucrare.dataset.carriers.get(subtype, {}):
            continue
        aggregate = anexa.annual.get(f"{parent.value}_tep")
        if aggregate is None or not isinstance(aggregate.value, int | float):
            continue
        covered.add(parent)
        derived = tep(prelucrare.dataset, prelucrare.factors, subtype, year)
        if derived.value is None:
            continue
        locations = prelucrare.located
        unknown = aggregate.displayed_decimals is None or any(
            key not in locations or locations[key].displayed_decimals is None
            for key in derived.inputs
        )
        if unknown:
            matches = math.isclose(
                float(aggregate.value), derived.value, rel_tol=1e-9, abs_tol=1e-9
            )
        else:
            checked = reconcile(
                float(aggregate.value),
                aggregate.displayed_decimals or 0,
                derived,
                [locations[key].displayed_decimals or 0 for key in derived.inputs],
            )
            matches = checked.status == "match"
        if not matches:
            conflicts.append(
                SourceDisagreement(
                    f"carrier_family.{parent.value}.{year}",
                    Reading(derived.value, "tep"),
                    Reading(float(aggregate.value), "tep"),
                    "prelucrare",
                    "anexa",
                    locations.get(derived.inputs[0]) if derived.inputs else None,
                    aggregate,
                )
            )
    return frozenset(covered), conflicts


def _necesar_locations(info: NecesarInfo) -> dict[str, Located]:
    result: dict[str, Located] = {}
    for carrier, block in info.carriers.items():
        for year, values in block.years.items():
            if values.total is not None:
                result[f"carrier.{carrier.value}.{year}"] = values.total
            for month, value in enumerate(values.months, 1):
                if value is not None:
                    result[f"carrier.{carrier.value}.{year}.{month:02d}"] = value
    return result


def _internal_disagreements(  # noqa: C901
    imported: PrelucrareData | None,
    dataset: EnergyDataset,
    factors: FactorTable,
    annual: AnnualCheck,
    locations: dict[str, Located],
) -> list[SourceDisagreement]:
    conflicts: list[SourceDisagreement] = []
    for yearly in annual.years:
        for check in (*yearly.components, *yearly.totals):
            if check.status != "conflict" or check.computed.value is None:
                continue
            if not isinstance(check.filed.value, int | float):
                raise ValueError(f"numeric filing required: {check.key}")
            computed_location = (
                locations.get(check.computed.inputs[0]) if check.computed.inputs else None
            )
            if check.source == "prelucrare_filed":
                chosen = Reading(float(check.filed.value), "tep")
                alternative = Reading(check.computed.value, "tep")
                chosen_source, alternative_source = "prelucrare_filed", "calculated"
                chosen_location, alternative_location = check.filed, computed_location
            else:
                chosen = Reading(check.computed.value, "tep")
                alternative = Reading(float(check.filed.value), "tep")
                chosen_source, alternative_source = "calculated", "anexa"
                chosen_location, alternative_location = computed_location, check.filed
            conflicts.append(
                SourceDisagreement(
                    check.key,
                    chosen,
                    alternative,
                    chosen_source,
                    alternative_source,
                    chosen_location,
                    alternative_location,
                )
            )
    if imported is None:
        return conflicts
    for year in range(annual.years[0].year, annual.years[-1].year + 1):
        for carrier in dataset.carriers:
            if not counts_in_total(carrier) or year not in dataset.carriers[carrier]:
                continue
            filed = imported.filed.get(f"co2.{carrier.value}.{year}")
            if filed is None or not isinstance(filed.value, int | float):
                continue
            computed = co2(dataset, factors, year, carrier)
            if computed.value is None or _same_filed(filed, computed, locations):
                continue
            conflicts.append(
                SourceDisagreement(
                    f"co2.{carrier.value}.{year}",
                    Reading(computed.value, "t CO₂"),
                    Reading(float(filed.value), "t CO₂"),
                    "calculated",
                    "prelucrare_filed",
                    locations.get(computed.inputs[0]) if computed.inputs else None,
                    filed,
                )
            )
    return conflicts


def _same_filed(filed: Located, computed: Derived, locations: dict[str, Located]) -> bool:
    if computed.value is None or not isinstance(filed.value, int | float):
        return False
    decimals = filed.displayed_decimals
    input_decimals = [
        locations[key].displayed_decimals for key in computed.inputs if key in locations
    ]
    if (
        decimals is None
        or len(input_decimals) != len(computed.inputs)
        or any(value is None for value in input_decimals)
    ):
        return math.isclose(float(filed.value), computed.value, rel_tol=1e-9, abs_tol=1e-9)
    return (
        reconcile(
            float(filed.value), decimals, computed, [cast(int, value) for value in input_decimals]
        ).status
        == "match"
    )


def assemble(
    year: int,
    anexa: AnexaData,
    necesar: NecesarInfo | None,
    prelucrare: PrelucrareData | None = None,
    previous_piee: Path | None = None,
) -> PieeData:
    """Keep preferred values while retaining every disagreement for review."""
    if anexa.year is not None and anexa.year.value != year:
        raise EmaError(
            "piee_annex_year", "Anul anexei nu corespunde perioadei PIEE.", str(anexa.year.value)
        )
    if necesar is None:
        required_years = set(range(year - 2, year + 1))
        if prelucrare is None or not required_years.issubset(prelucrare.dataset.years):
            raise EmaError(
                "piee_sources_incomplete",
                "Necesar info lipseşte, iar Prelucrare date nu acoperă toţi anii analizei.",
                ", ".join(str(item) for item in sorted(required_years)),
            )
        necesar_status = (
            "not needed: covered by Prelucrare (years "
            + ", ".join(str(item) for item in sorted(required_years))
            + ")"
        )
        necesar = NecesarInfo()
    else:
        necesar_status = "received"
    necesar_locations = _necesar_locations(necesar)
    family_aggregates, family_conflicts = _family_evidence(anexa, year, prelucrare)
    dataset, disagreements, anexa_locations = _merge_anexa(
        to_dataset(necesar), anexa, year, necesar_locations, family_aggregates
    )
    disagreements.extend(family_conflicts)
    locations = {**anexa_locations, **necesar_locations}
    factors = FACTORS_2026
    if prelucrare is not None:
        dataset, pre_conflicts = merge_prelucrare(dataset, prelucrare)
        disagreements.extend(
            SourceDisagreement(
                item.field,
                item.prelucrare,
                item.other,
                "prelucrare",
                "anexa" if item.field in anexa_locations else "necesar",
                prelucrare.located.get(item.field),
                locations.get(item.field),
            )
            for item in pre_conflicts
        )
        locations.update(prelucrare.located)
        factors = factors_for_output(prelucrare, dataset.years)
    annual = annual_check(
        anexa,
        year,
        dataset,
        factors,
        locations,
        prelucrare.filed if prelucrare is not None else None,
    )
    disagreements.extend(_internal_disagreements(prelucrare, dataset, factors, annual, locations))
    presented, conversion = presentation_dataset(dataset, previous_piee)
    pie_representation = (
        delivered_pie_representation(previous_piee) if previous_piee is not None else "normalized"
    )
    separate_pv = delivered_separate_pv_figures(previous_piee) if previous_piee else True
    return PieeData(
        year,
        anexa,
        necesar,
        prelucrare,
        presented,
        factors,
        tuple(disagreements),
        annual,
        necesar_status,
        conversion,
        pie_representation,
        "previous_piee" if previous_piee is not None else "base",
        separate_pv,
    )


def load(
    year: int,
    anexa: Path,
    necesar: Path | None,
    prelucrare: Path | None = None,
    previous_piee: Path | None = None,
) -> PieeData:
    return assemble(
        year,
        parse_anexa(anexa),
        parse_necesar_info(necesar) if necesar is not None else None,
        existing_piee_readings(import_prelucrare(prelucrare)) if prelucrare is not None else None,
        previous_piee,
    )
