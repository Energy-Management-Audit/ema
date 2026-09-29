"""S7 analysis plans for every catalogue section in audit chapter four."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from ema.audit.catalogue import CATALOGUE
from ema.audit.chapter_four_chart_text import is_turnover_unit, scaled_unit
from ema.consumption_analysis.analysis import Metric, SectionPlan, TablePlan, analyze, value
from ema.core.office.blocks import (
    Block,
    Caption,
    Missing,
    Num,
    Paragraph,
    Ref,
    Segment,
    Table,
)
from ema.core.office.missing_text import MISSING_TEXT, TABLE_MISSING_NOTE, TABLE_MISSING_TEXT
from ema.energy_data.carriers import WATER_CARRIERS, Carrier
from ema.energy_data.factors import FactorTable
from ema.energy_data.model import EnergyDataset

TITLES = {
    Carrier.electricity_grid: "Consumul de energie electrică din rețea",
    Carrier.electricity_pv: "Consumul de energie electrică fotovoltaică",
    Carrier.natural_gas: "Consumul de gaze naturale",
    Carrier.diesel: "Consumul de motorină",
    Carrier.petrol: "Consumul de benzină",
    Carrier.lpg: "Consumul de GPL",
    Carrier.fuel_oil: "Consumul de păcură",
    Carrier.clu: "Consumul de CLU",
    Carrier.coal: "Consumul de cărbune",
    Carrier.coke: "Consumul de cocs",
    Carrier.wood: "Consumul de lemn",
    Carrier.biomass: "Consumul de biomasă",
    Carrier.sunflower_husks: "Consumul de coji de floarea soarelui",
    Carrier.biogas: "Consumul de biogaz",
    Carrier.ctl: "Consumul de CTL",
    Carrier.purchased_heat: "Consumul de energie termică achiziționată",
    Carrier.water_potable: "Consumul de apă potabilă",
    Carrier.water_industrial: "Consumul de apă industrială",
    Carrier.water_storm: "Consumul de apă pluvială",
}
ELECTRIC = frozenset({Carrier.electricity_grid})
PV = frozenset({Carrier.electricity_pv})
GAS = frozenset({Carrier.natural_gas})
FUEL = frozenset({Carrier.diesel, Carrier.petrol, Carrier.lpg, Carrier.fuel_oil, Carrier.clu})


def _annual(  # noqa: PLR0913
    dataset: EnergyDataset,
    factors: FactorTable,
    metric: Metric,
    years: tuple[int, ...],
    unit: str,
    label: str,
    *,
    product_name: str | None = None,
) -> list[Block]:
    result: list[Block] = []
    for year in years:
        number, fact = value(dataset, factors, metric, year)
        if metric.kind in {"specific", "water_specific", "intensity"}:
            display_unit, scale = scaled_unit(unit, metric.kind)
            if number is None:
                product = f"{product_name or MISSING_TEXT}: " if product_name is not None else ""
                result.append(Missing("body", f"{product}pentru anul {year}: {MISSING_TEXT};"))
                continue
            prefix: list[Segment] = (
                [product_name or Num(None, 0), ": "] if product_name is not None else []
            )
            result.append(
                Paragraph(
                    "body",
                    [
                        *prefix,
                        f"pentru anul {year} s-a înregistrat o valoare de ",
                        Num(number * scale, 2, display_unit, fact, scale=scale),
                        ";",
                    ],
                )
            )
        else:
            result.append(Paragraph("body", [f"{label} {year}: ", Num(number, 2, unit, fact), "."]))
    return result


def _monthly(  # noqa: PLR0913
    dataset: EnergyDataset,
    factors: FactorTable,
    section: str,
    metric: Metric,
    years: tuple[int, ...],
    label: str | list[Segment],
    *,
    unit: str,
) -> list[Block]:
    result: list[Block] = []
    stage = (
        "production"
        if metric.kind == "production"
        else "equivalent"
        if metric.kind in {"tep", "tep_total"}
        else "carrier"
    )
    for first, proto in ((1, "months_first"), (7, "months_second")):
        metrics = tuple(replace(metric, month=month) for month in range(first, first + 6))
        plan = TablePlan(proto, metrics, years, grouping=True)
        table = analyze(dataset, factors, (SectionPlan(section, stage, (plan,)),))[0].blocks[0]
        assert isinstance(table, Table)
        table = replace(table, missing_text=TABLE_MISSING_TEXT)
        caption_id = f"{section}:{metric.carriers}:{metric.product}:{first}"
        result.append(
            Caption(
                "caption",
                "tab",
                caption_id,
                [
                    "Tabelul ",
                    Ref("tab", caption_id),
                    ". ",
                    *([label] if isinstance(label, str) else label),
                ],
            )
        )
        result.append(table)
        if any(
            isinstance(segment, Num) and segment.value is None
            for row in table.rows
            for cell in row
            for segment in cell
        ):
            result.append(Missing("body", TABLE_MISSING_NOTE))
    result.extend(_annual(dataset, factors, metric, years, unit, "Total anual"))
    return result


def _carriers(
    dataset: EnergyDataset,
    factors: FactorTable,
    section: str,
    allowed: frozenset[Carrier],
    *,
    equivalent: bool = False,
) -> list[Block]:
    result: list[Block] = []
    for carrier in dataset.carriers:
        if carrier not in allowed:
            continue
        years = tuple(year for year in dataset.years if year in dataset.carriers[carrier])
        if not years:
            continue
        label = TITLES[carrier]
        result.append(Paragraph("body", [label]))
        metric = Metric("tep" if equivalent else "carrier", (carrier,))
        series = dataset.carriers[carrier][years[0]]
        reading = series.annual or next(iter(series.months.values()), None)
        unit = "tep" if equivalent else reading.unit if reading else ""
        result.extend(_monthly(dataset, factors, section, metric, years, label, unit=unit))
    return result or [Missing("body", "[de completat]")]


def _production(dataset: EnergyDataset, factors: FactorTable, client: str) -> list[Block]:
    result: list[Block] = []
    for product, series in dataset.production.items():
        years = tuple(year for year in dataset.years if year in series)
        if not years:
            continue
        label = dataset.production_name.get(product, "")
        unit = dataset.production_unit.get(product, "")
        title: list[Segment] = [
            "Centralizator al "
            + ("cifrei lunare de afaceri" if is_turnover_unit(unit) else "producției lunare")
            + " înregistrate de către ",
            client or Num(None, 0),
        ]
        title.extend(
            [f" – {unit}/lună"]
            if is_turnover_unit(unit)
            else [" – ", label or Num(None, 0), "/lună"]
        )
        result.extend(
            _monthly(
                dataset,
                factors,
                "ch4.productie",
                Metric("production", product=product),
                years,
                title,
                unit=unit,
            )
        )
    return result or [Missing("body", "[de completat]")]


def _specific(
    dataset: EnergyDataset,
    factors: FactorTable,
    allowed: frozenset[Carrier] | None,
    *,
    water: bool = False,
) -> list[Block]:
    result: list[Block] = []
    for product in dataset.production:
        chosen = (
            [carrier for carrier in dataset.carriers if carrier in allowed]
            if allowed is not None
            else [None]
        )
        for carrier in chosen:
            metric = Metric(
                "water_specific" if water else "specific",
                (carrier,) if carrier is not None else (),
                product=product,
            )
            years = tuple(
                year
                for year in dataset.years
                if year in dataset.production[product]
                and (carrier is None or year in dataset.carriers[carrier])
            )
            if not years:
                continue
            label = TITLES[carrier] if carrier is not None else "Consum total"
            result.append(Paragraph("body", [label]))
            unit = ("m³" if water else "tep") + "/" + dataset.production_unit[product]
            products = [
                key
                for key, series in dataset.production.items()
                if any(
                    year in series and (carrier is None or year in dataset.carriers[carrier])
                    for year in dataset.years
                )
            ]
            name = dataset.production_name.get(product, "") if len(products) > 1 else None
            result.extend(_annual(dataset, factors, metric, years, unit, label, product_name=name))
    return result or [Missing("body", "[de completat]")]


def _written(text: str | None) -> list[Block]:
    paragraphs = [part.strip() for part in (text or "").split("\n\n") if part.strip()]
    if not paragraphs:
        return [Missing("body", "[de completat]")]
    return [Paragraph("body", [part]) for part in paragraphs]


def chapter_four_blocks(  # noqa: C901
    dataset: EnergyDataset,
    factors: FactorTable,
    *,
    texts: Mapping[str, str] | None = None,
    client: str = "",
) -> list[Block]:
    blocks: list[Block] = []
    raw = {
        "ch4.electricitate": ELECTRIC,
        "ch4.electricitate_pv": PV,
        "ch4.gaz": GAS,
        "ch4.carburant": FUEL,
        "ch4.apa": WATER_CARRIERS,
    }
    equivalent = {
        "ch4.echiv_electric": ELECTRIC,
        "ch4.echiv_pv": PV,
        "ch4.echiv_gaz": GAS,
        "ch4.echiv_carburant": FUEL,
    }
    specific = {
        "ch4.specific_electric": ELECTRIC,
        "ch4.specific_pv": PV,
        "ch4.specific_gaz": GAS,
        "ch4.specific_carburant": FUEL,
        "ch4.specific_apa": WATER_CARRIERS,
    }
    for section in (item for item in CATALOGUE if item.id.startswith("ch4.")):
        blocks.append(Paragraph("heading:" + section.id, [section.title]))
        if section.id == "ch4.productie":
            blocks.extend(_production(dataset, factors, client))
        elif section.id in raw:
            blocks.extend(_carriers(dataset, factors, section.id, raw[section.id]))
        elif section.id in equivalent:
            blocks.extend(
                _carriers(dataset, factors, section.id, equivalent[section.id], equivalent=True)
            )
        elif section.id == "ch4.echiv_total":
            blocks.extend(
                _monthly(
                    dataset,
                    factors,
                    section.id,
                    Metric("tep_total"),
                    dataset.years,
                    "Consum total echivalent",
                    unit="tep",
                )
            )
        elif section.id in specific:
            blocks.extend(
                _specific(
                    dataset,
                    factors,
                    specific[section.id],
                    water=section.id == "ch4.specific_apa",
                )
            )
        elif section.id == "ch4.specific_total":
            blocks.extend(_specific(dataset, factors, None))
        elif section.id == "ch4.intensitate":
            blocks.extend(
                _annual(
                    dataset,
                    factors,
                    Metric("intensity"),
                    dataset.years,
                    "tep/1000 lei",
                    "Intensitate energetică",
                )
            )
        elif section.id == "ch4.mediu":
            blocks.extend(
                _annual(dataset, factors, Metric("co2"), dataset.years, "t CO₂", "Emisii")
            )
        elif section.id in {"ch4.concluzii", "ch4.eficienta", "ch4.bilant_real"}:
            blocks.extend(_written((texts or {}).get(section.id)))
    return blocks
