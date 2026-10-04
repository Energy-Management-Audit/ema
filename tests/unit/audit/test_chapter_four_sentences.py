"""Synthetic arithmetic statements; no dossier material is committed."""

import json
from pathlib import Path

from ema.audit.chapter_four_sentences import sentence_plan, write_sentence_record
from ema.energy_data.carriers import Carrier
from ema.energy_data.factors import FACTORS_2026
from ema.energy_data.model import CarrierSeries, EnergyDataset, Reading


def _dataset(years: tuple[int, int] = (2024, 2025), first: float = 10) -> EnergyDataset:
    old, new = years
    return EnergyDataset(
        years,
        {
            Carrier.electricity_grid: {
                old: CarrierSeries(annual=Reading(first, "MWh")),
                new: CarrierSeries(annual=Reading(15, "MWh")),
            },
            Carrier.natural_gas: {
                old: CarrierSeries(annual=Reading(20, "MWh")),
                new: CarrierSeries(annual=Reading(10, "MWh")),
            },
        },
        turnover_lei={old: Reading(1_000_000, "lei"), new: Reading(1_000_000, "lei")},
    )


def test_every_sentence_shape_and_source_record(tmp_path: Path) -> None:
    plan = sentence_plan(_dataset(), FACTORS_2026)
    by_id = {item.template_id: item.text for item in plan.derivations}
    assert by_id["carrier_change"] == (
        "Consumul de gaze naturale a scăzut cu 50,00 % în 2025 față de 2024."
    )
    assert (
        "Ponderea consumului de gaze naturale în totalul de energie din 2025 a fost de 40,00 %."
        in [item.text for item in plan.derivations if item.template_id == "carrier_share"]
    )
    assert by_id["intensity_change"] == (
        "Intensitatea energetică a scăzut cu 16,67 % în 2025 față de 2024."
    )
    assert by_id["largest_share"] == (
        "Cea mai mare pondere în consumul total de energie din 2025 o are "
        "energie electrică din SEN: 60,00 %."
    )
    assert by_id["total_change"] == (
        "Consumul total echivalent a scăzut cu 16,67 % în 2025 față de 2024."
    )
    assert by_id["intensity_direction"] == (
        "Intensitatea energetică a înregistrat o tendință de scădere în 2025."
    )
    output = tmp_path / "ch4-sentences.json"
    write_sentence_record(output, plan)
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["notes"] == []
    assert saved["sentences"][0]["inputs"] == [
        ["carrier.electricity_grid.2024", 10],
        ["carrier.electricity_grid.2025", 15],
    ]
    assert saved["sentences"][0]["formula"] == "change.year"


def test_zero_baseline_and_nonconsecutive_years_refuse_change() -> None:
    zero = sentence_plan(_dataset(first=0), FACTORS_2026)
    assert "electricity_grid: 2024–2025: bază zero" in zero.notes
    assert not any(
        item.template_id == "carrier_change" and "energie electrică" in item.text
        for item in zero.derivations
    )
    gap = sentence_plan(_dataset((2023, 2025)), FACTORS_2026)
    assert any("ani neconsecutivi" in note for note in gap.notes)
    assert not any(item.template_id == "carrier_change" for item in gap.derivations)


def test_mismatched_units_refuse_change_without_losing_chapter() -> None:
    dataset = _dataset()
    dataset.carriers[Carrier.electricity_grid][2025] = CarrierSeries(annual=Reading(15_000, "kWh"))
    plan = sentence_plan(dataset, FACTORS_2026)
    assert "electricity_grid: 2024–2025: unități diferite" in plan.notes
    assert any(item.template_id == "largest_share" for item in plan.derivations)
    assert not any(
        item.template_id == "carrier_change" and "energie electrică" in item.text
        for item in plan.derivations
    )


def test_rounded_zero_changes_are_constant() -> None:
    dataset = EnergyDataset(
        (2024, 2025),
        {
            Carrier.electricity_grid: {
                2024: CarrierSeries(annual=Reading(10_000, "MWh")),
                2025: CarrierSeries(annual=Reading(10_000.04, "MWh")),
            }
        },
        turnover_lei={2024: Reading(1_000_000, "lei"), 2025: Reading(1_000_000, "lei")},
    )
    plan = sentence_plan(dataset, FACTORS_2026)
    by_id = {item.template_id: item.text for item in plan.derivations}
    for key in ("carrier_change", "intensity_change", "total_change"):
        assert "a rămas constant" in by_id[key]
        assert " cu " not in by_id[key]
    assert "stabilitate" in by_id["intensity_direction"]


def test_last_energy_year_precedes_later_turnover_and_refusals_are_recorded() -> None:
    dataset = _dataset()
    dataset = EnergyDataset(
        (2024, 2025, 2026),
        dataset.carriers,
        turnover_lei={**dataset.turnover_lei, 2026: Reading(2_000_000, "lei")},
    )
    plan = sentence_plan(dataset, FACTORS_2026)
    assert "din 2025" in next(
        item.text for item in plan.derivations if item.template_id == "largest_share"
    )
    assert any(item.template_id == "total_change" for item in plan.derivations)
    dataset.carriers[Carrier.natural_gas][2024] = CarrierSeries(annual=Reading(None, "MWh"))
    refused = sentence_plan(dataset, FACTORS_2026)
    assert any(note.startswith("total: 2024–2025:") for note in refused.notes)
    assert any(note.startswith("pondere: natural_gas:") for note in refused.notes)


def test_factor_record_carries_per_input_conversion(tmp_path: Path) -> None:
    plan = sentence_plan(_dataset(), FACTORS_2026)
    output = tmp_path / "ch4-sentences.json"
    write_sentence_record(output, plan)
    saved = json.loads(output.read_text(encoding="utf-8"))
    share = next(
        item
        for item in saved["sentences"]
        if item["template_id"] == "carrier_share" and "2025" in item["text"]
    )
    assert share["factor_version"] == FACTORS_2026.version
    assert ["carrier.electricity_grid.2025", 0.086] in share["tep_factors"]
    assert ["carrier.natural_gas.2025", 0.086] in share["tep_factors"]
