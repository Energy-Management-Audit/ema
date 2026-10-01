"""Render one sourced carrier group in the PIEE document."""

# pyright: reportPrivateUsage=false, reportUnusedFunction=false

from __future__ import annotations

from lxml import etree

from ema.core.office.anchors import AnchorLedger
from ema.energy_data.carriers import WATER_CARRIERS, Carrier
from ema.piee.chart_plan import ChartBinding, chart_series
from ema.piee.dataset import PieeData
from ema.piee.number import prototype_number
from ema.piee.section_clone_tools import (
    COGEN_BALANCE,
    VOCABULARY,
    Figure,
    _add_chart,
    _figure_series,
    _monthly_table,
    _paragraph,
)


def _carrier_group(  # noqa: PLR0913
    root: etree._Element,
    manifest: dict[str, dict[str, str | list[str]]],
    data: PieeData,
    carrier: Carrier,
    charts: dict[Figure, tuple[etree._Element, etree._Element]],
    *,
    ledger: AnchorLedger,
    next_id: list[int],
) -> list[etree._Element]:
    water = carrier in WATER_CARRIERS
    group = "water" if water else "gas"
    noun, heading, row_label = VOCABULARY[carrier]
    unit = (
        "m3"
        if water
        else next(
            (
                series.annual.unit
                for series in data.dataset.carriers[carrier].values()
                if series.annual
            ),
            "MWh",
        )
    )
    nodes = [
        _paragraph(
            root,
            manifest,
            group,
            "heading",
            heading,
            f"{carrier.value}_heading",
            ledger=ledger,
            next_id=next_id,
        ),
        _paragraph(
            root,
            manifest,
            group,
            "intro",
            f"{row_label or 'Consumul de ' + noun} este prezentat pentru "
            f"perioada {data.year - 2}–{data.year}.",
            f"{carrier.value}_intro",
            ledger=ledger,
            next_id=next_id,
        ),
    ]
    offsets = (-2, -1, 0) if not water or data.layout.water_monthly else ()
    for index, offset in enumerate(offsets):
        year = data.year + offset
        nodes.append(
            _paragraph(
                root,
                manifest,
                group,
                "monthly_intro",
                f"Consumul lunar de {noun} în {year} este prezentat în figura următoare.",
                f"{carrier.value}_monthly_intro_{index + 1}",
                ledger=ledger,
                next_id=next_id,
                n=index,
            )
        )
        _add_chart(
            nodes,
            charts[
                Figure(
                    "word/charts/chart" + str((21 if water else 13) + index) + ".xml",
                    carrier,
                    "monthly",
                    offset,
                )
            ],
            carrier,
            f"monthly_{index + 1}",
            ledger=ledger,
            next_id=next_id,
        )
        nodes.append(
            _paragraph(
                root,
                manifest,
                group,
                "monthly_observation",
                f"Consumul lunar de {noun} în {year} este prezentat mai sus.",
                f"{carrier.value}_monthly_observation_{index + 1}",
                ledger=ledger,
                next_id=next_id,
                n=index,
            )
        )
    if offsets:
        nodes.append(
            _paragraph(
                root,
                manifest,
                group,
                "table_intro",
                f"{row_label or 'Consumul de ' + noun} lunar este prezentat în tabelul următor.",
                f"{carrier.value}_table_intro",
                ledger=ledger,
                next_id=next_id,
            )
        )
        nodes.append(
            _paragraph(
                root,
                manifest,
                group,
                "table_caption",
                f"Tabelul 99 {row_label or 'Consumul de ' + noun}, {unit}/an",
                f"{carrier.value}_table_caption",
                ledger=ledger,
                next_id=next_id,
            )
        )
        for half in range(2):
            nodes.append(
                _monthly_table(
                    root, manifest, group, carrier, half, data, ledger=ledger, next_id=next_id
                )
            )
    nodes.append(
        _paragraph(
            root,
            manifest,
            group,
            "annual_intro",
            f"Consumul anual de {noun} este prezentat în figura următoare.",
            f"{carrier.value}_annual_intro",
            ledger=ledger,
            next_id=next_id,
        )
    )
    source = 24 if water else 16
    _add_chart(
        nodes,
        charts[Figure(f"word/charts/chart{source}.xml", carrier, "annual", None)],
        carrier,
        "annual",
        ledger=ledger,
        next_id=next_id,
    )
    nodes.append(
        _paragraph(
            root,
            manifest,
            group,
            "annual_observation",
            f"Evoluția anuală a consumului de {noun} este prezentată mai sus.",
            f"{carrier.value}_annual_observation",
            ledger=ledger,
            next_id=next_id,
        )
    )
    annual = _figure_series(data, Figure(f"word/charts/chart{source}.xml", carrier, "annual", None))
    if carrier == Carrier.electricity_cogen:
        nodes.append(
            _paragraph(
                root,
                manifest,
                group,
                "annual_intro",
                COGEN_BALANCE,
                f"{carrier.value}_balance_intro",
                ledger=ledger,
                next_id=next_id,
            )
        )
        grid = chart_series(data, ChartBinding("balance", "carrier", Carrier.electricity_grid))[0]
        for index, year in enumerate(range(data.year - 2, data.year + 1), 1):
            cogen = annual.values[index - 1]
            purchased = grid.values[index - 1] if grid else None
            total = purchased + cogen if purchased is not None and cogen is not None else None
            share = round(100 * cogen / total) if total and cogen is not None else None
            text = (
                f"{prototype_number(total, 2)} MWh/an din care {share}% o reprezintă ponderea "
                f"energiei electrice produsă intern prin cogenerare în {year}"
                f"{'.' if index == 3 else ';'}"
                if total is not None and share is not None
                else "n.d."
            )
            nodes.append(
                _paragraph(
                    root,
                    manifest,
                    group,
                    "annual_list_item",
                    text,
                    f"{carrier.value}_annual_list_item_{index}",
                    ledger=ledger,
                    next_id=next_id,
                )
            )
    else:
        if water and not data.layout.water_monthly:
            nodes.append(
                _paragraph(
                    root,
                    manifest,
                    group,
                    "annual_intro",
                    f"Consumul de apă {noun.removeprefix('apă ')} a fost:",
                    f"{carrier.value}_annual_list_intro",
                    ledger=ledger,
                    next_id=next_id,
                )
            )
        for index, year in enumerate(range(data.year - 2, data.year + 1), 1):
            amount = annual.values[index - 1]
            value = prototype_number(amount, 0 if water else 2) if amount is not None else "n.d."
            text = (
                f"în anul {year} de {value} m3/an{'.' if index == 3 else ','}"
                if water
                else (
                    f"pentru anul {year} s-au înregistrat {value} {unit}/an"
                    f"{'.' if index == 3 else ','}"
                )
            )
            nodes.append(
                _paragraph(
                    root,
                    manifest,
                    group,
                    "annual_list_item",
                    text,
                    f"{carrier.value}_annual_list_item_{index}",
                    ledger=ledger,
                    next_id=next_id,
                )
            )
    return nodes
