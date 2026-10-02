"""Source-backed native chart plans for the authored chapter-four tables."""

from __future__ import annotations

from dataclasses import dataclass

from ema.audit.catalogue import CATALOGUE
from ema.audit.chapter_four_blocks import FUEL, TITLES, emission_carriers
from ema.audit.chapter_four_chart_text import (
    ANNUAL,
    MONTHS,
    STYLE_PART,
    SUBJECT,
    WATER_ANNUAL,
    is_turnover_unit,
)
from ema.audit.chapter_four_chart_values import chart_series, display_unit, has_chart_data
from ema.consumption_analysis.analysis import Metric
from ema.consumption_analysis.metric_kind import MetricKind
from ema.core.office.blocks import Block, Missing, NativeChart, Paragraph
from ema.core.office.missing_text import MISSING_TEXT
from ema.energy_data.carriers import Carrier
from ema.energy_data.factors import FactorTable
from ema.energy_data.model import EnergyDataset


@dataclass(frozen=True)
class ChartGroup:
    label: str | None
    monthly: list[Block]
    annual: list[Block]


@dataclass(frozen=True)
class _Spec:
    section: str
    label: str | None
    series: tuple[tuple[str, Metric], ...]
    years: tuple[int, ...]
    unit: str
    subject: str | None = None
    monthly: bool = False
    annual_text: str | None = None
    production: bool = False


def _years(
    dataset: EnergyDataset, carriers: tuple[Carrier, ...], product: str | None = None
) -> tuple[int, ...]:
    return tuple(
        year
        for year in dataset.years
        if (product is None or year in dataset.production.get(product, {}))
        and (not carriers or any(year in dataset.carriers[carrier] for carrier in carriers))
    )


def _reading_unit(dataset: EnergyDataset, carriers: tuple[Carrier, ...]) -> set[str]:
    return {
        reading.unit
        for carrier in carriers
        for series in dataset.carriers[carrier].values()
        for reading in ([series.annual] if series.annual else []) + list(series.months.values())
    }


def _carrier_spec(  # noqa: PLR0913
    dataset: EnergyDataset,
    section: str,
    carriers: tuple[Carrier, ...],
    *,
    kind: MetricKind,
    monthly: bool = False,
    product: str | None = None,
    subject: str | None = None,
    label: str | None = None,
    annual_text: str | None = None,
) -> _Spec | None:
    if not carriers:
        return None
    years = _years(dataset, carriers, product)
    if not years:
        return None
    if kind == "carrier":
        units = _reading_unit(dataset, carriers)
        if len(units) != 1:
            return None
        unit = next(iter(units))
    elif kind == "water_specific":
        assert product is not None
        unit = "m³/" + dataset.production_unit[product]
    elif kind == "specific":
        assert product is not None
        unit = "tep/" + dataset.production_unit[product]
    else:
        unit = "tep"
    return _Spec(
        section,
        label,
        tuple((TITLES[carrier], Metric(kind, (carrier,), product=product)) for carrier in carriers),
        years,
        unit,
        subject,
        monthly,
        annual_text,
    )


def _specs(dataset: EnergyDataset) -> tuple[list[_Spec], list[str]]:  # noqa: C901, PLR0912
    result: list[_Spec] = []
    skipped: list[str] = []
    products = tuple(dataset.production)
    product = products[0] if len(products) == 1 else None
    if product is None:
        skipped.append("ch4.productie:products")
    else:
        years = tuple(year for year in dataset.years if year in dataset.production[product])
        if years:
            result.append(
                _Spec(
                    "ch4.productie",
                    None,
                    (
                        (
                            dataset.production_name.get(product, ""),
                            Metric("production", product=product),
                        ),
                    ),
                    years,
                    dataset.production_unit[product],
                    monthly=True,
                    production=True,
                )
            )
    raw = (
        ("ch4.electricitate", (Carrier.electricity_grid,)),
        ("ch4.gaz", (Carrier.natural_gas,)),
        ("ch4.carburant", tuple(carrier for carrier in dataset.carriers if carrier in FUEL)),
        (
            "ch4.apa",
            tuple(
                carrier
                for carrier in dataset.carriers
                if carrier
                in {
                    Carrier.water_potable,
                    Carrier.water_industrial,
                }
            ),
        ),
    )
    for section, allowed in raw:
        for carrier in allowed if section == "ch4.apa" else (None,):
            carriers = (
                (carrier,)
                if carrier is not None
                else tuple(c for c in allowed if c in dataset.carriers)
            )
            if section == "ch4.carburant" and len(_reading_unit(dataset, carriers)) > 1:
                skipped.append("ch4.carburant:units")
                break
            spec = _carrier_spec(
                dataset,
                section,
                carriers,
                kind="carrier",
                monthly=True,
                subject="consumului de carburant"
                if section == "ch4.carburant"
                else SUBJECT.get(carriers[0])
                if carriers
                else None,
                label=TITLES[carrier]
                if carrier is not None
                else TITLES[carriers[0]]
                if len(carriers) == 1
                else None,
            )
            if spec is not None:
                result.append(spec)
    for section, carriers in (
        ("ch4.echiv_electric", (Carrier.electricity_grid,)),
        ("ch4.echiv_gaz", (Carrier.natural_gas,)),
        ("ch4.echiv_carburant", tuple(carrier for carrier in dataset.carriers if carrier in FUEL)),
    ):
        available = tuple(carrier for carrier in carriers if carrier in dataset.carriers)
        spec = _carrier_spec(dataset, section, available, kind="tep", annual_text=ANNUAL[section])
        if spec is not None:
            result.append(spec)
    result.append(
        _Spec(
            "ch4.echiv_total",
            None,
            (("Consum total echivalent", Metric("tep_total")),),
            dataset.years,
            "tep",
            annual_text=ANNUAL["ch4.echiv_total"],
        )
    )
    if product is None:
        skipped.extend(
            f"{section}:products"
            for section in (
                "ch4.specific_electric",
                "ch4.specific_gaz",
                "ch4.specific_carburant",
                "ch4.specific_total",
                "ch4.specific_apa",
            )
        )
    else:
        for section, carriers in (
            ("ch4.specific_electric", (Carrier.electricity_grid,)),
            ("ch4.specific_gaz", (Carrier.natural_gas,)),
            (
                "ch4.specific_carburant",
                tuple(carrier for carrier in dataset.carriers if carrier in FUEL),
            ),
        ):
            available = tuple(carrier for carrier in carriers if carrier in dataset.carriers)
            spec = _carrier_spec(
                dataset,
                section,
                available,
                kind="specific",
                product=product,
                annual_text=ANNUAL[section],
            )
            if spec is not None:
                result.append(spec)
        result.append(
            _Spec(
                "ch4.specific_total",
                "Consum total",
                (("Consum total", Metric("specific", product=product)),),
                _years(dataset, (), product),
                "tep/" + dataset.production_unit[product],
                annual_text=ANNUAL["ch4.specific_total"],
            )
        )
        for carrier in (Carrier.water_potable, Carrier.water_industrial):
            if carrier not in dataset.carriers:
                continue
            spec = _carrier_spec(
                dataset,
                "ch4.specific_apa",
                (carrier,),
                kind="water_specific",
                product=product,
                label=TITLES[carrier],
                annual_text=WATER_ANNUAL[carrier],
            )
            if spec is not None:
                result.append(spec)
    result.extend(
        (
            _Spec(
                "ch4.intensitate",
                None,
                (("Intensitate energetică", Metric("intensity")),),
                dataset.years,
                "tep/1000 lei",
                annual_text=ANNUAL["ch4.intensitate"],
            ),
            _Spec(
                "ch4.mediu",
                None,
                (("Emisii", Metric("co2", emission_carriers(dataset))),),
                dataset.years,
                "t CO₂",
                annual_text=ANNUAL["ch4.mediu"],
            ),
        )
    )
    if Carrier.electricity_pv in dataset.carriers:
        skipped.extend(
            f"{section}:electricity_pv"
            for section in (
                "ch4.electricitate_pv",
                "ch4.echiv_pv",
                "ch4.specific_pv",
            )
        )
    if Carrier.water_storm in dataset.carriers:
        skipped.extend(f"{section}:water_storm" for section in ("ch4.apa", "ch4.specific_apa"))
    return result, skipped


def _caption(spec: _Spec, client: str, k: int, letter: str | None, year: int | None) -> str:
    prefix = f"Fig. nr. 4.{k} " + (f"{letter}) " if letter else "")
    if spec.production:
        if year is not None:
            subject = (
                "cifrei lunare de afaceri" if is_turnover_unit(spec.unit) else "producției lunare"
            )
            return (
                prefix + f"Evoluția lunară a {subject} înregistrate de către {client} "
                f"la nivelul anului {year}"
            )
        return prefix + f"Evoluția anuală a producției înregistrate la nivelul {client}"
    if spec.annual_text is not None:
        return prefix + spec.annual_text.format(client=client)
    assert spec.subject is not None
    if year is not None:
        return (
            prefix + f"Evoluția lunară a {spec.subject} înregistrat de către {client} "
            f"la nivelul anului {year}"
        )
    return prefix + f"Evoluția anuală a {spec.subject} înregistrat la nivelul {client}"


def _group(
    dataset: EnergyDataset,
    factors: FactorTable,
    spec: _Spec,
    client: str,
    k: int,
    skipped: list[str],
) -> ChartGroup:
    monthly: list[Block] = []
    key = spec.section
    if spec.section in {"ch4.apa", "ch4.specific_apa"}:
        key += ":" + spec.series[0][1].carriers[0].value
    metrics = tuple(metric for _, metric in spec.series)
    unit, scale = display_unit(dataset, factors, metrics, spec.unit, spec.years)
    letter = 0
    if spec.monthly:
        for year in spec.years:
            series = chart_series(dataset, factors, spec.series, scale, list(MONTHS), year)
            caption = _caption(spec, client, k, chr(ord("a") + letter), year)
            letter += 1
            if not has_chart_data(series):
                monthly.append(Missing("body", f"{caption}: {MISSING_TEXT}"))
                skipped.append(f"{key}:{year}:no_data")
                continue
            monthly.extend(
                (
                    NativeChart("chart", STYLE_PART, series, column_axis_title=unit + "/lună"),
                    Paragraph(
                        "chart_caption",
                        [caption, "", "", ""],
                    ),
                )
            )
    annual_series = chart_series(
        dataset, factors, spec.series, scale, [str(year) for year in spec.years], None
    )
    annual: list[Block] = []
    caption = _caption(spec, client, k, chr(ord("a") + letter) if letter else None, None)
    if has_chart_data(annual_series):
        axis = (
            unit
            if spec.series[0][1].kind in {"specific", "water_specific", "intensity"}
            else unit + "/an"
        )
        annual.extend(
            (
                NativeChart("chart", STYLE_PART, annual_series, column_axis_title=axis),
                Paragraph(
                    "chart_caption",
                    [
                        caption,
                        "",
                        "",
                        "",
                    ],
                ),
            )
        )
    else:
        annual.append(Missing("body", f"{caption}: {MISSING_TEXT}"))
        skipped.append(f"{key}:annual:no_data")
    return ChartGroup(spec.label, monthly, annual)


def chapter_chart_groups(
    dataset: EnergyDataset, factors: FactorTable, client: str
) -> tuple[dict[str, list[ChartGroup]], list[str]]:
    specs, skipped = _specs(dataset)
    groups: dict[str, list[ChartGroup]] = {}
    number = 1
    for section in (item.id for item in CATALOGUE if item.id.startswith("ch4.")):
        for spec in (item for item in specs if item.section == section):
            group = _group(dataset, factors, spec, client, number, skipped)
            if group.monthly or group.annual:
                groups.setdefault(section, []).append(group)
                number += 1
    return groups, skipped


def chart_blocks(
    section_id: str, dataset: EnergyDataset, factors: FactorTable, client: str
) -> tuple[list[Block], list[str]]:
    groups, skipped = chapter_chart_groups(dataset, factors, client)
    return [
        block for group in groups.get(section_id, []) for block in (*group.monthly, *group.annual)
    ], [key for key in skipped if key.startswith(section_id + ":")]
