"""S7 analysis plans for every catalogue section in audit chapter four."""

from __future__ import annotations

from collections.abc import Mapping

from ema.audit.catalogue import CATALOGUE
from ema.audit.chapter_four_annual import annual as _annual
from ema.audit.chapter_four_annual import annual_carrier_table, annual_only_sentence
from ema.audit.chapter_four_chart_text import is_turnover_unit
from ema.audit.chapter_four_comments import (
    RESOURCE,
    factor_key,
    intro,
    period,
    table_lead,
)
from ema.audit.chapter_four_intensity import intensity_table
from ema.audit.chapter_four_resources import (
    ELECTRIC,
    FUEL,
    GAS,
    PV,
    TITLES,
    monthly_tables,
    resource_blocks,
)
from ema.audit.chapter_four_sentences import sentence_plan
from ema.audit.chapter_four_water import without_empty_water
from ema.consumption_analysis.analysis import Metric, value
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
from ema.energy_data.carriers import CARRIER_NAMES_RO, WATER_CARRIERS, Carrier, counts_in_total
from ema.energy_data.factors import FactorTable
from ema.energy_data.model import EnergyDataset, annual_only

EMISSIONS_MISSING = "n.d."
# a carrier the client has no series for in that year is not part of that year's total
NO_SERIES = "–"


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
            monthly_tables(
                dataset,
                factors,
                "ch4.productie",
                Metric("production", product=product),
                years,
                title,
                unit=unit,
                subject="cifrei de afaceri" if is_turnover_unit(unit) else "producției",
            )
        )
    return result or [Missing("body", "[de completat]")]


def _specific(
    dataset: EnergyDataset,
    factors: FactorTable,
    section: str,
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
            yearly = carrier is not None and annual_only(dataset.carriers[carrier])
            if carrier is not None and yearly:
                result.append(annual_only_sentence(carrier))
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
            if carrier is not None and yearly:
                result.extend(
                    annual_carrier_table(
                        dataset,
                        factors,
                        metric,
                        years,
                        unit,
                        label=label,
                        section=section,
                        subject=(
                            "consumului specific de "
                            if water
                            else "consumului specific echivalent de "
                        )
                        + RESOURCE[carrier],
                    )
                )
            result.extend(_annual(dataset, factors, metric, years, unit, label, product_name=name))
    return result or [Missing("body", "[de completat]")]


def emission_carriers(dataset: EnergyDataset) -> tuple[Carrier, ...]:
    """Purchased energy only: self-generated PV has no emission factor and no row in her table."""
    return tuple(
        sorted(
            (
                carrier
                for carrier in dataset.carriers
                if counts_in_total(carrier) and carrier != Carrier.electricity_pv
            ),
            key=list(Carrier).index,
        )
    )


def _emissions(dataset: EnergyDataset, factors: FactorTable, notes: tuple[str, ...]) -> list[Block]:
    carriers = emission_carriers(dataset)
    if not carriers:
        return [Missing("body", "[de completat]")]
    years = dataset.years
    rows: list[list[list[Segment]]] = []
    for label, metric in (
        *((CARRIER_NAMES_RO[carrier], Metric("co2", (carrier,))) for carrier in carriers),
        ("Total", Metric("co2", carriers)),
    ):
        cells: list[list[Segment]] = [[label[:1].upper() + label[1:]]]
        for year in years:
            if label != "Total" and not all(
                year in dataset.carriers.get(c, {}) for c in metric.carriers
            ):
                cells.append([NO_SERIES])
                continue
            number, fact = value(dataset, factors, metric, year, filed=False)
            cells.append([Num(number, 2, fact=fact, grouping=True)])
        rows.append(cells)
    caption = Caption(
        "caption",
        "tab",
        "ch4.mediu",
        ["Tabelul ", Ref("tab", "ch4.mediu"), ". Emisii de gaze cu efect de seră – t CO₂"],
    )
    table = Table(
        "emissions", rows, header=[["Sursa", *map(str, years)]], missing_text=EMISSIONS_MISSING
    )
    factor_list: list[Block] = [
        Paragraph(f"emission_note:{i}", [text]) for i, text in enumerate(notes)
    ] or [Missing("body", "[de completat]")]
    lead = table_lead("ch4.mediu", f"emisiile de gaze cu efect de seră {period(years)}")
    return [lead, caption, table, *factor_list]


def _written(text: str | None) -> list[Block]:
    paragraphs = [part.strip() for part in (text or "").split("\n\n") if part.strip()]
    if not paragraphs:
        return [Missing("body", "[de completat]")]
    return [Paragraph("body", [part]) for part in paragraphs]


def chapter_four_blocks(  # noqa: C901, PLR0912
    dataset: EnergyDataset,
    factors: FactorTable,
    *,
    texts: Mapping[str, str] | None = None,
    client: str = "",
    notes: tuple[str, ...] = (),
) -> list[Block]:
    blocks: list[Block] = intro(dataset, client) if dataset.years else []
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
    dataset = without_empty_water(dataset)
    sentences = sentence_plan(dataset, factors).sections
    no_water = not any(carrier in WATER_CARRIERS for carrier in dataset.carriers)
    for section in (item for item in CATALOGUE if item.id.startswith("ch4.")):
        if no_water and section.id in {"ch4.apa", "ch4.specific_apa"}:
            continue
        blocks.append(Paragraph("heading:" + section.id, [section.title]))
        if section.id == "ch4.productie":
            blocks.extend(_production(dataset, factors, client))
        elif section.id in raw:
            key = factor_key(section.id).removeprefix("narrative.")
            blocks.extend(
                resource_blocks(
                    dataset,
                    factors,
                    section.id,
                    raw[section.id],
                    factor_text=(texts or {}).get(key),
                )
            )
        elif section.id in equivalent:
            blocks.extend(
                resource_blocks(
                    dataset, factors, section.id, equivalent[section.id], equivalent=True
                )
            )
        elif section.id == "ch4.echiv_total":
            blocks.extend(
                monthly_tables(
                    dataset,
                    factors,
                    section.id,
                    Metric("tep_total"),
                    dataset.years,
                    "Consum total echivalent",
                    unit="tep",
                    subject="consumului total echivalent de energie",
                )
            )
        elif section.id in specific:
            blocks.extend(
                _specific(
                    dataset,
                    factors,
                    section.id,
                    specific[section.id],
                    water=section.id == "ch4.specific_apa",
                )
            )
        elif section.id == "ch4.specific_total":
            blocks.extend(_specific(dataset, factors, section.id, None))
        elif section.id == "ch4.intensitate":
            blocks.extend(intensity_table(dataset, factors))
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
            blocks.extend(_emissions(dataset, factors, notes))
        elif section.id in {"ch4.concluzii", "ch4.eficienta", "ch4.bilant_real"}:
            written = (texts or {}).get(section.id)
            arithmetic = sentences.get(section.id, [])
            blocks.extend(arithmetic)
            if written:
                blocks.extend(_written(written))
            elif not arithmetic:
                blocks.extend(_written(None))
        if section.id not in {"ch4.concluzii", "ch4.eficienta", "ch4.bilant_real"}:
            blocks.extend(sentences.get(section.id, []))
    return blocks
