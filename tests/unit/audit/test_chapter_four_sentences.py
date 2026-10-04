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
        "Consumul de gaze naturale a scăzut cu 50,00 % în 2025 faţă de 2024."
    )
    assert (
        "Ponderea consumului de gaze naturale în totalul de energie din 2025 a fost de 40,00 %."
        in [item.text for item in plan.derivations if item.template_id == "carrier_share"]
    )
    assert by_id["intensity_change"] == (
        "Intensitatea energetică a scăzut cu 16,67 % în 2025 faţă de 2024."
    )
    assert by_id["largest_share"] == (
        "În 2025, ponderea cea mai mare în consumul total de energie a revenit "
        "energie electrică din SEN: 60,00 %."
    )
    assert by_id["total_change"] == (
        "Consumul total echivalent a scăzut cu 16,67 % în 2025 faţă de 2024."
    )
    assert by_id["intensity_direction"] == (
        "Intensitatea energetică a înregistrat o tendinţă de scădere în 2025."
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
