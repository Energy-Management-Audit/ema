"""Ch. 4 share pies: the carrier mix of the total and the PV share of electricity."""

from __future__ import annotations

from ema.audit.chapter_four_blocks import FUEL
from ema.audit.chapter_four_chart_text import STYLE_PART
from ema.core.office.blocks import Block, Missing, NativeChart, Paragraph
from ema.core.office.chart_series import Series
from ema.core.office.missing_text import MISSING_TEXT
from ema.core.office.pie_xml import COLOURS, PieKind
from ema.energy_data.calc import annual, tep
from ema.energy_data.carriers import CARRIER_NAMES_RO, Carrier, counts_in_total
from ema.energy_data.factors import FactorTable
from ema.energy_data.model import Derived, EnergyDataset

MIX_GROUPS: tuple[tuple[str, frozenset[Carrier]], ...] = (
    ("Energie electrică din SEN", frozenset({Carrier.electricity_grid})),
    ("Energie electrică fotovoltaică", frozenset({Carrier.electricity_pv})),
    ("Gaze naturale", frozenset({Carrier.natural_gas})),
    ("Carburant", FUEL),
)
# The PIEE PV_LABELS wording, copied because workflows never import each other.
PV_LABELS = (
    "Energia electrică achiziționată din SEN",
    "Energia electrică consumată din sistemul fotovoltaic propriu",
)
MIX_LEAD = (
    "În ceea ce privește ponderile diverselor resurse energetice în total consum energetic "
    "înregistrat de către societate în perioada de analiză, în figurile cu numărul 4.{k} "
    "sunt prezentate aceste informații.",
    "În ceea ce privește ponderile diverselor resurse energetice în total consum energetic "
    "înregistrat de către societate în perioada de analiză, în figura numărul 4.{k} "
    "sunt prezentate aceste informații.",
)
PV_LEAD = (
    "În figurile cu numărul 4.{k} se prezintă ponderea energiei electrice consumată din "
    "parcul fotovoltaic propriu din total energie electrică consumată în perioada de analiză "
    "la nivelul societății.",
    "În figura numărul 4.{k} se prezintă ponderea energiei electrice consumată din "
    "parcul fotovoltaic propriu din total energie electrică consumată în perioada de analiză "
    "la nivelul societății.",
)

type _Slices = tuple[tuple[str, ...], tuple[float, ...]]
type _Year = tuple[str, _Slices | None]


def _figures(kind: PieKind, k: int, lead: tuple[str, str], years: list[_Year]) -> list[Block]:
    """Lead-in, then per year a pie and caption or a marker; letters only past one figure."""
    if not years:
        return []
    single = len(years) == 1
    blocks: list[Block] = [Paragraph("body", [(lead[1] if single else lead[0]).format(k=k)])]
    for index, (subject, slices) in enumerate(years):
        caption = f"Fig. nr. 4.{k} " + ("" if single else f"{chr(ord('a') + index)}) ") + subject
        if slices is None:
            blocks.append(Missing("body", f"{caption}: {MISSING_TEXT}"))
            continue
        labels, values = slices
        total = sum(values)
        series = Series("Pondere", list(labels), [value / total for value in values])
        blocks.extend(
            (
                NativeChart("chart", STYLE_PART, [series], pie=kind),
                Paragraph("chart_caption", [caption, "", "", ""]),
            )
        )
    return blocks


def _mix_slices(
    dataset: EnergyDataset, factors: FactorTable, year: int
) -> list[tuple[str, float | None]]:
    others = tuple(
        (CARRIER_NAMES_RO[carrier][:1].upper() + CARRIER_NAMES_RO[carrier][1:], {carrier})
        for carrier in Carrier
        if counts_in_total(carrier) and not any(carrier in group for _, group in MIX_GROUPS)
    )
    result: list[tuple[str, float | None]] = []
    for label, group in (*MIX_GROUPS, *others):
        present = [c for c in Carrier if c in group and year in dataset.carriers.get(c, {})]
        if not present:
            continue
        values = [tep(dataset, factors, carrier, year).value for carrier in present]
        result.append((label, None if None in values else sum(v for v in values if v is not None)))
    return result


def _mix_gap(slices: list[tuple[str, float | None]]) -> str | None:
    if any(value is None for _, value in slices):
        return "no_data"
    if len(slices) < 2:
        return "single_carrier"
    if len(slices) > len(COLOURS):
        return "too_many_slices"
    if sum(value or 0.0 for _, value in slices) == 0:
        return "no_data"
    return None


def mix_pies(
    dataset: EnergyDataset, factors: FactorTable, client: str, k: int, skipped: list[str]
) -> list[Block]:
    """One carrier-mix pie per year for ``ch4.echiv_total``."""
    years: list[_Year] = []
    for year in dataset.years:
        subject = (
            "Ponderea diverselor surse de energie în total consum înregistrat în cadrul "
            f"{client} la nivelul anului {year}"
        )
        slices = _mix_slices(dataset, factors, year)
        reason = _mix_gap(slices)
        if reason is not None:
            skipped.append(f"ch4.echiv_total:pie:{year}:{reason}")
        if reason == "single_carrier":
            continue
        labels = tuple(label for label, _ in slices)
        values = tuple(value or 0.0 for _, value in slices)
        years.append((subject, None if reason else (labels, values)))
    return _figures("mix", k, MIX_LEAD, years)


def _pv_gap(totals: list[Derived], values: list[float]) -> str | None:
    if len(values) < 2:
        return "no_data"
    if totals[0].unit != totals[1].unit:
        return "unit_mismatch"
    if sum(values) == 0:
        return "no_data"
    return None


def pv_pies(
    dataset: EnergyDataset, factors: FactorTable, client: str, k: int, skipped: list[str]
) -> list[Block]:
    """One SEN/PV share pie per PV year for ``ch4.electricitate_pv``."""
    pv = dataset.carriers.get(Carrier.electricity_pv, {})
    years: list[_Year] = []
    for year in (year for year in dataset.years if year in pv):
        subject = (
            "Ponderea energiei electrice consumată din parcul fotovoltaic propriu din total "
            f"energie electrică la nivelul anului {year}"
        )
        totals = [
            annual(series, "carrier", carrier.value, year)
            for carrier in (Carrier.electricity_grid, Carrier.electricity_pv)
            if (series := dataset.carriers.get(carrier, {}).get(year)) is not None
        ]
        values = [total.value for total in totals if total.value is not None]
        reason = _pv_gap(totals, values)
        if reason is not None:
            skipped.append(f"ch4.electricitate_pv:pie:{year}:{reason}")
        years.append((subject, None if reason else (PV_LABELS, tuple(values))))
    return _figures("pv", k, PV_LEAD, years)
