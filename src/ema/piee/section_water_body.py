"""Fill the approved base's potable-water slots from sourced readings."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from docx.oxml.ns import qn
from lxml import etree

from ema.core.office.anchors import AnchorLedger, find
from ema.core.office.cell_text import set_cell_text, set_paragraph_text
from ema.energy_data.carriers import Carrier
from ema.piee.chart_plan import MONTHS, ChartBinding, chart_series
from ema.piee.dataset import PieeData
from ema.piee.number import prototype_number
from ema.piee.section_clone_tools import _present


def _set(root: etree._Element, ledger: AnchorLedger, slot: str, content: str) -> None:
    set_paragraph_text(find([root], slot), content, missing=content == "n.d.")
    ledger.record(slot)


def _value(amount: float | None, decimals: int) -> str:
    return prototype_number(amount, decimals) if amount is not None else "n.d."


def _table(
    root: etree._Element, ledger: AnchorLedger, slot: str, data: PieeData, half: int
) -> None:
    marker = find([root], slot)
    table = next(marker.iterancestors(qn("w:tbl")), None)
    if table is None:
        raise ValueError("water prototype table missing")
    for row_index, row in enumerate(table.findall(qn("w:tr"))[:4]):
        for column, cell in enumerate(row.findall(qn("w:tc"))[:7]):
            if row_index == 0:
                content = "Anul" if column == 0 else MONTHS[half * 6 + column - 1]
            elif column == 0:
                content = str(data.year - 3 + row_index)
            else:
                series = chart_series(
                    data,
                    ChartBinding("water", "water", Carrier.water_potable, row_index - 3),
                )[0]
                amount = series.values[half * 6 + column - 1] if series else None
                content = _value(amount, 0)
            set_cell_text(cell, content, missing=content == "n.d.")
    for bookmark in table.iter(qn("w:bookmarkStart")):
        name = (bookmark.get(qn("w:name")) or "").removeprefix("_ema_")
        if name in ledger.expected:
            ledger.record(name)


def render_potable_water(  # noqa: C901
    root: etree._Element,
    manifest: dict[str, dict[str, str | list[str]]],
    data: PieeData,
    ledger: AnchorLedger,
) -> None:
    """Write annual and optional monthly values; no base-client water remains."""
    if not _present(data, Carrier.water_potable):
        return
    for slot in (
        "section_water_start",
        "section_specific_water_start",
        "section_electricity_pv_end",
    ):
        if slot in ledger.expected:
            ledger.record(slot)
    _set(
        root,
        ledger,
        "body_237",
        f"Consumul de apă potabilă în perioada {data.year - 2}–{data.year} este prezentat mai jos.",
    )
    if data.layout.water_monthly:
        for index, year in enumerate(range(data.year - 2, data.year + 1)):
            for number, content in (
                (
                    238 + index * 5,
                    f"Consumul lunar de apă potabilă în {year} este prezentat mai jos.",
                ),
                (
                    240 + index * 5,
                    f"Fig. nr. 99 Evoluția lunară a consumului de apă potabilă în {year}",
                ),
                (241 + index * 5, ""),
                (
                    242 + index * 5,
                    f"Valorile lunare ale consumului de apă potabilă în {year} "
                    "sunt prezentate în figură.",
                ),
            ):
                _set(root, ledger, f"body_{number}", content)
            ledger.record(f"body_{239 + index * 5}")
        _set(
            root,
            ledger,
            "body_253",
            "Consumul lunar de apă potabilă este prezentat în tabelul următor.",
        )
        _set(root, ledger, "body_254", "Tabelul 99 Consumul de apă potabilă, m3/an")
        for slot in ("body_255", "body_256", "body_258", "body_260"):
            ledger.record(slot)
        for half in range(2):
            raw = manifest["water"]["table"]
            assert isinstance(raw, list)
            _table(root, ledger, raw[half], data, half)
    _set(
        root,
        ledger,
        "body_261",
        "Consumul anual de apă potabilă este prezentat în figura următoare.",
    )
    ledger.record("body_262")
    _set(root, ledger, "body_263", "Fig. nr. 99 Evoluția anuală a consumului de apă potabilă")
    ledger.record("body_265")
    _set(
        root,
        ledger,
        "body_266",
        "Evoluția anuală a consumului de apă potabilă este prezentată mai sus.",
    )
    _set(root, ledger, "body_267", "Consumul de apă potabilă a fost:")
    annual = chart_series(data, ChartBinding("water", "water", Carrier.water_potable))[0]
    specific = chart_series(data, ChartBinding("specific", "specific", Carrier.water_potable))[0]
    for index, year in enumerate(range(data.year - 2, data.year + 1)):
        suffix = "." if index == 2 else ","
        amount = annual.values[index] if annual else None
        _set(
            root,
            ledger,
            f"body_{268 + index}",
            f"în anul {year} de {_value(amount, 0)} m3/an{suffix}",
        )
    _set(
        root,
        ledger,
        "body_343",
        "Consumul specific de apă potabilă este prezentat în figura următoare.",
    )
    ledger.record("body_344")
    _set(
        root,
        ledger,
        "body_345",
        "Fig. nr. 99 Evoluția anuală a consumului specific de apă potabilă, m3/tone",
    )
    ledger.record("body_346")
    _set(
        root,
        ledger,
        "body_347",
        "Evoluția anuală a consumului specific de apă potabilă este prezentată mai sus.",
    )
    _set(root, ledger, "body_348", "Consumul specific de apă potabilă a fost:")
    for index, year in enumerate(range(data.year - 2, data.year + 1)):
        amount = specific.values[index] if specific else None
        suffix = "." if index == 2 else ","
        _set(
            root,
            ledger,
            f"body_{349 + index}",
            f"în anul {year} de {_value(amount, 4)} m3/tone{suffix}",
        )
