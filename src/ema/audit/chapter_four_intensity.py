"""The annual intensity table, using the chapter-four emissions-width prototype."""

from ema.consumption_analysis.analysis import Metric, value
from ema.core.office.blocks import Block, Caption, Num, Ref, Segment, Table
from ema.core.office.missing_text import TABLE_MISSING_TEXT
from ema.energy_data.calc import energy_intensity
from ema.energy_data.factors import FactorTable
from ema.energy_data.model import EnergyDataset


def intensity_table(dataset: EnergyDataset, factors: FactorTable) -> list[Block]:
    years = dataset.years
    if not years:
        return []
    rows: list[list[list[Segment]]] = [[["Intensitate energetică"]]]
    for year in years:
        result = energy_intensity(dataset, factors, year, filed=False)
        _, fact = value(dataset, factors, Metric("intensity"), year, filed=False)
        rows[0].append(
            [
                Num(
                    result.value * 1000 if result.value is not None else None,
                    2,
                    fact=fact,
                    scale=1000,
                )
            ]
        )
    return [
        Caption(
            "caption",
            "tab",
            "ch4.intensitate",
            [
                "Tabelul ",
                Ref("tab", "ch4.intensitate"),
                ". Evoluția intensității energetice (tep/mil lei)",
            ],
        ),
        Table(
            "emissions",
            rows,
            header=[["Indicator", *map(str, years)]],
            missing_text=TABLE_MISSING_TEXT,
        ),
    ]
