"""Add sourced carrier figures absent from the approved PIEE base."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from ema.consumption_analysis.analysis import Metric, value
from ema.core.office.anchor_targets import chart_target
from ema.core.office.chart_series import Series
from ema.core.office.charts import clone_chart
from ema.core.office.package import read_parts
from ema.energy_data.carriers import Carrier
from ema.piee.chart_plan import ChartBinding, chart_series
from ema.piee.dataset import PieeData
from ema.piee.figure_numbering import numbered_caption
from ema.piee.pies import expanded_mix

BIOMASS = (
    (Carrier.sunflower_husks, "coji de floarea-soarelui"),
    (Carrier.wood, "lemn"),
    (Carrier.biomass, "biomasă"),
)


def _annual_fuel(data: PieeData) -> list[Series]:
    binding = ChartBinding("extra_fuel_annual", "fuel")
    labels = ("Motorină", "Benzină", "GPL")
    return [
        Series(label, series.categories, series.values)
        for label, series in zip(labels, chart_series(data, binding), strict=True)
        if series is not None
    ]


def _biomass(data: PieeData) -> tuple[Carrier, str] | None:
    return next(
        ((carrier, label) for carrier, label in BIOMASS if carrier in data.dataset.carriers),
        None,
    )


def _biomass_series(
    data: PieeData, carrier: Carrier, label: str, offset: int | None
) -> Series | None:
    binding = ChartBinding("extra_biomass", "carrier", carrier, offset)
    series = chart_series(data, binding)[0]
    return Series(label, series.categories, series.values) if series is not None else None


def _specific_biomass(data: PieeData, carrier: Carrier, label: str) -> Series | None:
    binding = ChartBinding("extra_specific_biomass", "specific", carrier)
    series = chart_series(data, binding)[0]
    return (
        Series(
            "consum specific anual de "
            f"{label}, tep/{next(iter(data.dataset.production_unit.values()))}",
            series.categories,
            series.values,
        )
        if series is not None
        else None
    )


def _specific_mix(data: PieeData, year: int) -> Series | None:
    mixture = expanded_mix(data, year)
    product = next(iter(data.dataset.production), None)
    if mixture is None or product is None:
        return None
    production = value(data.dataset, data.factors, Metric("production", product=product), year)[0]
    if production is None or production <= 0:
        return None
    labels, amounts = mixture
    return Series("Pondere", list(labels), [amount / production for amount in amounts])


def render_extra_figures(source: Path, data: PieeData, output: Path) -> None:  # noqa: C901
    """Clone matching native prototypes for filed biomass and authored figure kinds."""
    if data.pie_representation_source != "previous_piee":
        output.write_bytes(source.read_bytes())
        return
    with TemporaryDirectory() as directory:
        current = source
        step = 0

        def add(style: str, after: str, series: list[Series], caption: str) -> str | None:
            nonlocal current, step
            if not series:
                return
            following = Path(directory) / f"figure-{step}.docx"
            part = clone_chart(
                current,
                style,
                series,
                None,
                following,
                after_part=after,
                caption=numbered_caption(current, caption),
            )
            current = following
            step += 1
            return part

        annual_fuel = _annual_fuel(data)
        fuel_after = "word/charts/chart20.xml"
        if annual_fuel:
            fuel_after = (
                add(
                    "word/charts/chart17.xml",
                    "word/charts/chart20.xml",
                    annual_fuel,
                    "Fig. Consumul anual de carburant, pe tipuri",
                )
                or fuel_after
            )
        biomass = _biomass(data)
        if biomass is not None:
            carrier, label = biomass
            for offset in (None, 0, -1, -2):
                series = _biomass_series(data, carrier, label, offset)
                if series is None:
                    continue
                annual = offset is None
                add(
                    "word/charts/chart16.xml" if annual else "word/charts/chart13.xml",
                    fuel_after,
                    [series],
                    f"Fig. Consumul {'anual' if annual else 'lunar'} de {label}"
                    + ("" if annual else f" în {data.year + offset}"),
                )
            specific = _specific_biomass(data, carrier, label)
            if specific is not None:
                add(
                    "word/charts/chart26.xml",
                    "word/charts/chart27.xml",
                    [specific],
                    f"Fig. Consumul specific anual de {label}",
                )
        for year, slot in (
            (data.year, "pie_rId38"),
            (data.year - 1, "pie_rId37"),
            (data.year - 2, "pie_rId36"),
        ):
            series = _specific_mix(data, year)
            if series is None:
                continue
            part = chart_target(read_parts(current), slot).part
            if part is None:
                raise ValueError(f"pie {slot} has no chart part")
            add(
                part,
                "word/charts/chart28.xml",
                [series],
                f"Fig. Ponderea consumului specific de energie în {year}",
            )
        share = chart_series(data, ChartBinding("extra_energy_share", "energy_share"))[0]
        if share is not None:
            add(
                "word/charts/chart30.xml",
                "word/charts/chart30.xml",
                [
                    Series(
                        "Ponderea energiei în valoarea producției", share.categories, share.values
                    )
                ],
                "Fig. Trendul ponderii energiei în valoarea producției",
            )
        output.write_bytes(current.read_bytes())
