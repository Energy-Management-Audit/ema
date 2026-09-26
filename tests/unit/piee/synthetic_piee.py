"""A small synthetic PIEE dataset shared by the review-overlay and import-stage tests."""

from __future__ import annotations

from typing import Any

from ema.core.office.sheets import CellRef
from ema.energy_data.anexa_cells import AnexaData, Measure
from ema.energy_data.carriers import Carrier
from ema.energy_data.factors import FACTORS_2026
from ema.energy_data.model import CarrierSeries, EnergyDataset, FiledValue, Reading
from ema.energy_data.necesar_model import NecesarInfo
from ema.energy_data.prelucrare_types import PrelucrareData
from ema.energy_data.source import Located
from ema.piee.annual_check import AnnualCheck
from ema.piee.dataset import PieeData

YEAR = 2025


def located(value: Any, row: int = 1, sheet: str = "Anexa") -> Located:
    return Located(value, CellRef(sheet, row, 2))


def piee_data(*, prelucrare: bool = True) -> PieeData:
    months = {month: Reading(100.0, "MWh") for month in range(1, 13)}
    dataset = EnergyDataset(
        (YEAR,),
        {
            Carrier.electricity_grid: {YEAR: CarrierSeries(months, Reading(1200.0, "MWh"))},
            Carrier.natural_gas: {YEAR: CarrierSeries({}, Reading(500.0, "MWh"))},
        },
        filed_indicators={"intensity": {YEAR: FiledValue(1.5, "tep/1000 lei", 2, "prelucrare")}},
    )
    measures = [
        Measure(
            "planned",
            located("Izolare"),
            located(2026),
            {
                "investment_thousand_lei": located(100.0),
                "saving_thousand_lei": located(25.0),
                "payback_years": located(4.0),
            },
        ),
        Measure("planned", located("Iluminat"), None, {"saving_mwh": located(10.0)}),
    ]
    anexa = AnexaData(identity={"name": located("Exemplu SA")}, planned_measures=measures)
    filed = {
        f"tep.electricity_grid.{YEAR}": located(103.2, sheet="TEP"),
        f"tep.electricity_grid.{YEAR}.03": located(8.6, sheet="TEP"),
        f"tep.total.{YEAR}": located(146.0, sheet="TEP"),
        f"tep.total.{YEAR}.03": located(12.2, sheet="TEP"),
        f"specific.total.{YEAR}": located(0.4, sheet="Consumuri specifice"),
    }
    return PieeData(
        YEAR,
        anexa,
        NecesarInfo(),
        PrelucrareData(dataset, FACTORS_2026, filed=filed) if prelucrare else None,
        dataset,
        FACTORS_2026,
        (),
        AnnualCheck("match", None, None),
    )
