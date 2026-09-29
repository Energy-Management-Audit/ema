"""Pure checks for quantities that the auditor's measurement sheet assesses."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ema.core.resources import resource_path
from ema.core.review.models import Field


@dataclass(frozen=True)
class Assessment:
    rule: str
    status: str
    fields: tuple[str, ...]


def _norms() -> dict[str, Any]:
    with resource_path("audit", "measurement_norms.json").open(encoding="utf-8") as handle:
        return json.load(handle)


def assess(fields: list[Field]) -> list[Assessment]:
    """Return pass, fail or unsupported; pending values do not enter a rule."""
    confirmed = [
        field
        for field in fields
        if field.value is not None
        and field.review in {"accepted", "corrected"}
        and not field.needs_confirmation
    ]
    grouped: dict[str, list[Field]] = {}
    for field in confirmed:
        grouped.setdefault(field.key.split(".")[-2], []).append(field)
    norms = _norms()
    results: list[Assessment] = []
    for quantity, values in grouped.items():
        numbers = [Decimal(str(field.value)) for field in values]
        keys = tuple(field.key for field in values)
        if quantity in {"voltage_ln", "voltage_ll"}:
            nominals = [Decimal(str(value)) for value in norms["voltage"]["nominal_v"]]
            tolerance = Decimal(str(norms["voltage"]["tolerance"]))
            valid = all(
                abs((number * (1000 if field.unit == "kV" else 1)) - nominal) <= nominal * tolerance
                for field, number in zip(values, numbers, strict=True)
                for nominal in [
                    min(
                        nominals,
                        key=lambda n: abs(n - number * (1000 if field.unit == "kV" else 1)),
                    )
                ]
            )
            results.append(Assessment("voltage", "pass" if valid else "fail", keys))
        elif quantity == "frequency":
            low, high = (Decimal(str(value)) for value in norms["frequency"]["normal_hz"])
            results.append(
                Assessment(
                    "frequency", "pass" if all(low <= n <= high for n in numbers) else "fail", keys
                )
            )
        elif quantity == "thd_u":
            limit = Decimal(str(norms["thd_u"]["max_percent"]))
            results.append(
                Assessment("thd_u", "pass" if all(n <= limit for n in numbers) else "fail", keys)
            )
        elif quantity == "thd_i":
            results.append(Assessment("thd_i", "unsupported", keys))
        elif quantity == "current":
            results.append(Assessment("current_asymmetry", "unsupported", keys))
        elif quantity == "power_factor":
            limit = Decimal(str(norms["power_factor"]["min"]))
            results.append(
                Assessment(
                    "power_factor", "pass" if all(n >= limit for n in numbers) else "fail", keys
                )
            )
        else:
            results.append(Assessment(quantity, "unsupported", keys))
    return results
