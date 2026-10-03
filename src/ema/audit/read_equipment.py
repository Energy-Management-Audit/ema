"""The ch. 3 equipment rows of the Necesar info as review fields, each with its cell evidence."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace

from ema.core.review.models import Field
from ema.energy_data.necesar_equipment import NecesarEquipment, Row
from ema.energy_data.source import normal

# The key families the render reads; a row's number comes second: audit.boiler.<n>.<role>.
BOILER, FORKLIFT, VEHICLE, TRANSFORMER = (
    "audit.boiler.",
    "audit.forklift.",
    "audit.vehicle.",
    "audit.transformer.",
)

Recorder = Callable[..., Field]

_LABELS = {
    BOILER: {
        "name": "Denumire",
        "process": "Proces deservit",
        "count": "Număr de bucăţi",
        "year": "An PIF",
        "load": "Grad mediu de încărcare",
        "power": "Putere instalată",
    },
    FORKLIFT: {
        "name": "Marca",
        "type": "Tip şi serie",
        "fuel": "Combustibil",
        "capacity": "Greutate şi înălţime de ridicare",
        "year": "An fabricaţie",
        "hours": "Ore de funcţionare",
        "location": "Locaţie",
    },
    VEHICLE: {
        "name": "Denumire",
        "maker": "Producător",
        "type": "Tip",
        "count": "Număr de bucăţi",
        "year": "An fabricaţie",
        "km": "Km parcurşi",
        "fuel": "Tip combustibil",
        "owner": "Proprietar",
    },
}
_TITLES = {
    BOILER: "Centrala termică",
    FORKLIFT: "Autostivuitor",
    VEHICLE: "Autovehicul",
    TRANSFORMER: "Transformator",
}


def _record_row(record: Recorder, sha: str, family: str, number: int, row: Row) -> list[Field]:
    result: list[Field] = []
    for role, cell in row.items():
        label = f"{_TITLES[family]} {number} – {_LABELS[family][role]}"
        # A year or a count the sheet fills with text ("2015-2016") stays text.
        whole = isinstance(cell.value, int)
        kind = "year" if whole and role == "year" else None
        decimals = 0 if whole else None
        result.append(
            record(
                f"{family}{number}.{role}",
                replace(cell, label=label),
                sha,
                "questionnaire",
                value_type=kind,
                unit=cell.unit,
                chapter="ch3",
                decimals=decimals,
            )
        )
    return result


def _property(label: str) -> str:
    return re.sub(r"\W+", "_", normal(label)).strip("_")


def equipment_fields(equipment: NecesarEquipment, record: Recorder, sha: str) -> list[Field]:
    result: list[Field] = []
    for family, rows in (
        (BOILER, equipment.boilers),
        (FORKLIFT, equipment.forklifts),
        (VEHICLE, equipment.vehicles),
    ):
        for number, row in enumerate(rows, 1):
            result.extend(_record_row(record, sha, family, number, row))
    for number, unit in enumerate(equipment.transformers, 1):
        for label, cell in unit.items():
            result.append(
                record(
                    f"{TRANSFORMER}{number}.{_property(label)}",
                    replace(cell, label=f"{_TITLES[TRANSFORMER]} {number} – {label}"),
                    sha,
                    "questionnaire",
                    chapter="ch3",
                    value_type=None,
                    unit=None,
                    decimals=None,
                )
            )
    return result
