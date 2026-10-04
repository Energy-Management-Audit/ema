"""Arithmetic-only Romanian chapter-four statements and their source record."""

from __future__ import annotations

import json
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from ema.core.office.blocks import Paragraph
from ema.core.office.numbers_ro import format_number
from ema.energy_data.calc import annual, change, energy_intensity, shares, tep, tep_total
from ema.energy_data.carriers import CARRIER_NAMES_RO, Carrier, counts_in_total
from ema.energy_data.factors import FactorTable
from ema.energy_data.model import Derived, EnergyDataset


@dataclass(frozen=True)
class SentenceDerivation:
    template_id: str
    text: str
    inputs: tuple[tuple[str, float], ...]
    formula: str


@dataclass(frozen=True)
class SentencePlan:
    sections: dict[str, list[Paragraph]]
    derivations: list[SentenceDerivation]
    notes: list[str]


def write_sentence_record(path: Path, plan: SentencePlan) -> None:
    path.write_text(
        json.dumps(
            {
                "sentences": [
                    {
                        "template_id": item.template_id,
                        "text": item.text,
                        "inputs": item.inputs,
                        "formula": item.formula,
                    }
                    for item in plan.derivations
                ],
                "notes": plan.notes,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def change_refusal(previous: Derived, current: Derived) -> str | None:
    """One refusal rule for both chapter text and review warnings."""
    result = change(previous, current)
    if "year.not_consecutive" in result.missing:
        return "ani neconsecutivi"
    if "previous.zero" in result.missing:
        return "bază zero"
    if result.value is None:
        return "date insuficiente"
    return None


def _add(
    sections: dict[str, list[Paragraph]],
    records: list[SentenceDerivation],
    section: str,
    template: str,
    text: str,
    formula: str,
    *inputs: Derived,
) -> None:
    sections.setdefault(section, []).append(Paragraph("body", [text]))
    records.append(
        SentenceDerivation(
            template,
            text,
            tuple(
                (key, float(value.value))
                for value in inputs
                if value.value is not None
                for key in value.inputs
            ),
            formula,
        )
    )


def _section(carrier: Carrier) -> str | None:
    if carrier == Carrier.electricity_grid:
        return "ch4.electricitate"
    if carrier == Carrier.electricity_pv:
        return "ch4.electricitate_pv"
    if carrier == Carrier.natural_gas:
        return "ch4.gaz"
    if carrier in {Carrier.diesel, Carrier.petrol, Carrier.lpg, Carrier.fuel_oil, Carrier.clu}:
        return "ch4.carburant"
    return None


def _source_value(dataset: EnergyDataset, key: str) -> float | None:
    parts = key.split(".")
    if len(parts) >= 3 and parts[0] == "carrier" and parts[1] in Carrier._value2member_map_:
        series = dataset.carriers.get(Carrier(parts[1]), {}).get(int(parts[2]))
        reading = (
            series.months.get(int(parts[3]))
            if series and len(parts) == 4
            else (series.annual if series else None)
        )
        return reading.value if reading else None
    if len(parts) == 2 and parts[0] == "turnover":
        reading = dataset.turnover_lei.get(int(parts[1]))
        return reading.value if reading else None
    if len(parts) >= 3 and parts[0] == "production":
        series = dataset.production.get(parts[1], {}).get(int(parts[2]))
        reading = (
            series.months.get(int(parts[3]))
            if series and len(parts) == 4
            else (series.annual if series else None)
        )
        return reading.value if reading else None
    return None


def sentence_plan(  # noqa: C901, PLR0912, PLR0915
    dataset: EnergyDataset, factors: FactorTable
) -> SentencePlan:
    sections: dict[str, list[Paragraph]] = {}
    records: list[SentenceDerivation] = []
    notes: list[str] = []
    for carrier, series in dataset.carriers.items():
        section = _section(carrier)
        if section is None:
            continue
        years = sorted(series)
        for previous_year, year in pairwise(years):
            before = annual(series[previous_year], "carrier", carrier.value, previous_year)
            after = annual(series[year], "carrier", carrier.value, year)
            reason = change_refusal(before, after)
            if reason:
                notes.append(f"{carrier.value}: {previous_year}–{year}: {reason}")
                continue
            difference = change(before, after)
            assert difference.value is not None
            verb = (
                "a crescut"
                if difference.value > 0
                else "a scăzut"
                if difference.value < 0
                else "a rămas constant"
            )
            text = (
                f"Consumul de {CARRIER_NAMES_RO[carrier]} {verb} cu "
                f"{format_number(abs(difference.value), 2)} % în {year} faţă de {previous_year}."
            )
            _add(sections, records, section, "carrier_change", text, "change.year", before, after)
    for year in dataset.years:
        total = tep_total(dataset, factors, year)
        for carrier, share in shares(dataset, factors, year).items():
            if share.value is None or total.value is None:
                continue
            part = tep(dataset, factors, carrier, year)
            text = (
                f"Ponderea consumului de {CARRIER_NAMES_RO[carrier]} în totalul de energie "
                f"din {year} a fost de {format_number(share.value, 2)} %."
            )
            _add(
                sections,
                records,
                "ch4.echiv_total",
                "carrier_share",
                text,
                "part / total * 100",
                part,
                total,
            )
    for previous_year, year in pairwise(dataset.years):
        before = energy_intensity(dataset, factors, previous_year, filed=False)
        after = energy_intensity(dataset, factors, year, filed=False)
        reason = change_refusal(before, after)
        if reason:
            notes.append(f"intensitate: {previous_year}–{year}: {reason}")
            continue
        difference = change(before, after)
        assert difference.value is not None
        direction = (
            "a crescut"
            if difference.value > 0
            else "a scăzut"
            if difference.value < 0
            else "a rămas constantă"
        )
        text = (
            f"Intensitatea energetică {direction} cu {format_number(abs(difference.value), 2)} % "
            f"în {year} faţă de {previous_year}."
        )
        _add(
            sections,
            records,
            "ch4.intensitate",
            "intensity_change",
            text,
            "change.year",
            before,
            after,
        )
    if dataset.years:
        year = dataset.years[-1]
        values = [
            (carrier, share)
            for carrier, share in shares(dataset, factors, year).items()
            if share.value is not None and counts_in_total(carrier)
        ]
        if values:
            carrier, biggest = max(values, key=lambda item: (item[1].value or 0, item[0].value))
            text = (
                f"În {year}, ponderea cea mai mare în consumul total de energie a revenit "
                f"{CARRIER_NAMES_RO[carrier]}: {format_number(biggest.value or 0, 2)} %."
            )
            _add(
                sections,
                records,
                "ch4.concluzii",
                "largest_share",
                text,
                "max(share.carrier)",
                biggest,
            )
        if len(dataset.years) >= 2:
            previous_year = dataset.years[-2]
            before, after = (
                tep_total(dataset, factors, candidate) for candidate in (previous_year, year)
            )
            if change_refusal(before, after) is None:
                difference = change(before, after)
                assert difference.value is not None
                direction = (
                    "a crescut"
                    if difference.value > 0
                    else "a scăzut"
                    if difference.value < 0
                    else "a rămas constant"
                )
                text = (
                    f"Consumul total echivalent {direction} cu "
                    f"{format_number(abs(difference.value), 2)} % "
                    f"în {year} faţă de {previous_year}."
                )
                _add(
                    sections,
                    records,
                    "ch4.concluzii",
                    "total_change",
                    text,
                    "change.year",
                    before,
                    after,
                )
            before_i = energy_intensity(dataset, factors, previous_year, filed=False)
            after_i = energy_intensity(dataset, factors, year, filed=False)
            if change_refusal(before_i, after_i) is None:
                difference_i = change(before_i, after_i)
                assert difference_i.value is not None
                direction_i = (
                    "creştere"
                    if difference_i.value > 0
                    else "scădere"
                    if difference_i.value < 0
                    else "stabilitate"
                )
                text_i = (
                    f"Intensitatea energetică a înregistrat o tendinţă de {direction_i} în {year}."
                )
                _add(
                    sections,
                    records,
                    "ch4.concluzii",
                    "intensity_direction",
                    text_i,
                    "sign(change.year)",
                    before_i,
                    after_i,
                )
    sourced = [
        SentenceDerivation(
            item.template_id,
            item.text,
            tuple(
                (key, value)
                for key, _ in dict(item.inputs).items()
                if (value := _source_value(dataset, key)) is not None
            ),
            item.formula,
        )
        for item in records
    ]
    return SentencePlan(sections, sourced, notes)
