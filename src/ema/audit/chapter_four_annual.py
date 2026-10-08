"""Annual chapter-four values and compact tables for annual-only carriers."""

from ema.audit.chapter_four_chart_values import display_unit
from ema.audit.chapter_four_comments import period, table_lead
from ema.consumption_analysis.analysis import Metric, value
from ema.core.office.blocks import Block, Caption, Missing, Num, Paragraph, Ref, Segment, Table
from ema.core.office.missing_text import MISSING_TEXT, TABLE_MISSING_TEXT
from ema.energy_data.carriers import CARRIER_NAMES_RO, Carrier
from ema.energy_data.factors import FactorTable
from ema.energy_data.model import EnergyDataset


def annual(  # noqa: PLR0913
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
    numbers = [value(dataset, factors, metric, year, filed=False) for year in years]
    shown_unit, scale = display_unit(dataset, factors, (metric,), unit, years)
    for year, (number, fact) in zip(years, numbers, strict=True):
        if metric.kind in {"specific", "water_specific", "intensity"}:
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
                        Num(number * scale, 2, shown_unit, fact, scale=scale),
                        ";",
                    ],
                )
            )
        else:
            result.append(Paragraph("body", [f"{label} {year}: ", Num(number, 2, unit, fact), "."]))
    return result


def annual_carrier_table(  # noqa: PLR0913
    dataset: EnergyDataset,
    factors: FactorTable,
    metric: Metric,
    years: tuple[int, ...],
    unit: str,
    *,
    label: str,
    section: str,
    subject: str,
) -> list[Block]:
    carrier = metric.carriers[0]
    caption_id = (
        f"{section}:{carrier.value}:{metric.product}:annual"
        if metric.product
        else f"{section}:{carrier.value}:annual"
    )
    shown_unit, scale = display_unit(dataset, factors, (metric,), unit, years)
    cells: list[list[Segment]] = [[f"Valoare ({shown_unit})"]]
    for year in years:
        number, fact = value(dataset, factors, metric, year, filed=False)
        cells.append(
            [Num(number * scale if number is not None else None, 2, fact=fact, scale=scale)]
        )
    return [
        table_lead(caption_id, f"evoluția anuală a {subject} {period(years)}"),
        Caption(
            "caption",
            "tab",
            caption_id,
            ["Tabelul ", Ref("tab", caption_id), f". {label} ({shown_unit})"],
        ),
        # Horizontal, like the emissions prototype it is drawn on: one column per year.
        Table(
            "emissions",
            [cells],
            header=[["Anul", *[str(year) for year in years]]],
            missing_text=TABLE_MISSING_TEXT,
        ),
    ]


def annual_only_sentence(carrier: Carrier) -> Paragraph:
    return Paragraph(
        "body", [f"Pentru {CARRIER_NAMES_RO[carrier]} au fost transmise numai consumurile anuale."]
    )
