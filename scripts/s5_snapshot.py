"""Write local, untracked S5 cell snapshots directly from the three .xls inputs."""

from __future__ import annotations

import json
import os
from pathlib import Path

import xlrd

from ema.energy_data.carriers import carrier_for
from ema.energy_data.source import normal

CASES = {
    "CLIENT-P1": "piee/cases/piee-case-a/received/Necesar info 2025 - CLIENT-P1 - completat .xls",
    "CLIENT-A3": (
        "audit/cases/audit-case-c/received/Necesar info aferente anului 2025 - "
        "CLIENT-A3 - 16.03.2026.xls"
    ),
    "CLIENT-A1": "audit/cases/audit-case-a/received/0.Necesar info CLIENT-A1 _2026.xls",
}
WATER = {"water_potable", "water_industrial", "water_storm"}


def _number(raw: object) -> float | None:
    if raw == "":
        return None
    if isinstance(raw, int | float):
        return float(raw)
    if isinstance(raw, str):
        return float(raw.strip().replace(" ", "").replace(".", "").replace(",", "."))
    raise ValueError(f"unexpected snapshot cell type: {type(raw).__name__}")


def snapshot(path: Path) -> dict[str, dict[str, dict[str, object]]]:
    book = xlrd.open_workbook(path)
    name = next(name for name in book.sheet_names() if normal(name) == "cons energetice")
    sheet = book.sheet_by_name(name)
    result: dict[str, dict[str, dict[str, object]]] = {}
    current: str | None = None
    for row in range(sheet.nrows):
        label = sheet.cell_value(row, 0)
        if isinstance(label, str) and normal(label).startswith("consum "):
            carrier = carrier_for(label)
            current = carrier.value if carrier is not None and carrier.value not in WATER else None
            continue
        if current is None or not isinstance(label, int | float) or not 2000 <= label <= 2100:
            continue
        if label != int(label):
            continue
        physical = row + 1
        values = [_number(sheet.cell_value(physical, col)) for col in range(1, 14)]
        result.setdefault(current, {})[str(int(label))] = {
            "row": physical + 1,
            "months": values[:12],
            "total": values[12],
        }
    book.release_resources()
    return result


def main() -> None:
    reference = Path(os.environ["EMA_REFERENCE"])
    output = (
        Path(os.environ.get("EMA_ARTIFACTS", "~/Code/projects/ema/artifacts")).expanduser()
        / "s5/expected"
    )
    output.mkdir(parents=True, exist_ok=True)
    for case, relative in CASES.items():
        data = snapshot(reference / relative)
        target = output / f"{case}.json"
        target.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        print(f"{case}: {sum(len(years) for years in data.values())} year groups -> {target}")


if __name__ == "__main__":
    main()
