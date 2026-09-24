"""Apply S7 chart values to the approved PIEE base figure slots."""

from __future__ import annotations

from pathlib import Path

from ema.core.office.anchors import AnchorLedger
from ema.core.office.chart_rewrite import remove_chart, rewrite_bar_chart
from ema.core.office.package import read_parts, write_parts
from ema.piee.chart_plan import BINDINGS, chart_series
from ema.piee.dataset import PieeData


def render_bar_charts(source: Path, data: PieeData, output: Path, ledger: AnchorLedger) -> None:
    """Change every base chart via its bookmark; missing figures lose their parts."""
    parts = read_parts(source)
    for binding in BINDINGS:
        series = chart_series(data, binding)
        if any(item is not None for item in series):
            rewrite_bar_chart(
                parts,
                binding.slot,
                series,
                cache_name_override="" if binding.slot == "chart_31" else None,
            )
            ledger.record(binding.slot)
        else:
            remove_chart(parts, binding.slot)
            ledger.record(binding.slot, removed=True)
    write_parts(parts, output)
