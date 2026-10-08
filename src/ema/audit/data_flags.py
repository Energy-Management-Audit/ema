"""Non-blocking, source-backed suspicions in audit review fields."""

from __future__ import annotations

from collections.abc import Mapping
from itertools import pairwise
from statistics import median

from ema.audit.chapter_four_sentences import change_refusal
from ema.audit.render_dataset import COST_KEYS, carrier_cost
from ema.core.office.numbers_ro import format_number
from ema.core.review.models import Field, Issue
from ema.energy_data.carriers import CARRIER_NAMES_RO, Carrier
from ema.energy_data.model import Derived
from ema.energy_data.prelucrare_tables import MONTHS

QUARTER_FACTOR = 2.5


def _carrier(code: str) -> Carrier | None:
    try:
        return Carrier(code)
    except ValueError:
        return None


def _number(field: Field | None) -> float | None:
    if field is None or field.value is None or field.value_type != "number":
        return None
    return float(field.value)


def _issue(code: str, message: str, *fields: Field) -> Issue | None:
    evidence = tuple(dict.fromkeys(ref for field in fields for ref in field.evidence))
    if len(evidence) < 2:
        return None
    return Issue(code=code, field_id=fields[0].id, message=message, evidence_ids=evidence)


def _paired_flags(fields: Mapping[str, Field]) -> list[Issue]:  # noqa: C901
    result: list[Issue] = []
    for key, field in sorted(fields.items()):
        if key.startswith("audit.economics."):
            for carrier, cost_key in COST_KEYS.items():
                prefix = f"audit.economics.{cost_key}."
                if not key.startswith(prefix) or not key[len(prefix) :].isdigit():
                    continue
                year = int(key[len(prefix) :])
                cost = carrier_cost(fields, carrier, year)
                quantity_key = f"carrier.{carrier.value}.{year}"
                quantities = [
                    quantity
                    for candidate, quantity in sorted(fields.items())
                    if candidate == quantity_key or candidate.startswith(f"{quantity_key}.")
                ]
                if cost is None or any((_number(q) or 0) > 0 for q in quantities):
                    continue
                name = CARRIER_NAMES_RO[carrier]
                message = (
                    f"{name[0].upper() + name[1:]}: {format_number(cost.value, 2)} lei "
                    f"declarate în {year}, fără consum în foaia de consumuri. "
                    "Consumul primează; costul nu este folosit."
                )
                issue = (
                    _issue("data_cost_without_quantity", message, quantities[0], cost)
                    if quantities
                    else Issue(
                        code="data_cost_without_quantity",
                        field_id=cost.id,
                        message=message,
                        evidence_ids=tuple(cost.evidence),
                    )
                )
                if issue:
                    result.append(issue)
        if not key.endswith(".count") or field.confidence != "conflict":
            continue
        for index, first in enumerate(field.alternatives):
            second = next(
                (item for item in field.alternatives[index + 1 :] if item.value != first.value),
                None,
            )
            if second is None:
                continue
            evidence = tuple(dict.fromkeys((*first.evidence, *second.evidence)))
            if len(evidence) >= 2:
                result.append(
                    Issue(
                        code="data_count_conflict",
                        field_id=field.id,
                        message=f"Număr diferit în două documente: {field.label}.",
                        evidence_ids=evidence,
                    )
                )
                break
    return result


def _series(fields: Mapping[str, Field]) -> dict[str, dict[int, Field]]:
    """Monthly series by their auditor-facing label, e.g. `motorină 2025`."""
    result: dict[str, dict[int, Field]] = {}
    for key, field in fields.items():
        parts = key.split(".")
        if (
            len(parts) != 4
            or parts[0] != "carrier"
            or not all(part.isdigit() for part in parts[2:])
        ):
            continue
        carrier = _carrier(parts[1])
        month = int(parts[3])
        if carrier is not None and 1 <= month <= 12:
            result.setdefault(f"{CARRIER_NAMES_RO[carrier]} {parts[2]}", {})[month] = field
    return result


def _monthly_flags(name: str, months: dict[int, Field]) -> list[Issue]:
    result: list[Issue] = []
    for month in range(1, 12):
        first, second = months.get(month), months.get(month + 1)
        if first is None or second is None or _number(first) in (None, 0):
            continue
        if _number(second) not in (None, 0) and _number(first) == _number(second):
            issue = _issue(
                "data_month_repeat",
                f"Luni consecutive egale: {name}, {MONTHS[month - 1]} şi {MONTHS[month]}.",
                first,
                second,
            )
            if issue:
                result.append(issue)
    for month, field in sorted(months.items()):
        number = _number(field)
        peers = [
            other
            for index, other in months.items()
            if index != month and _number(other) not in (None, 0)
        ]
        if number is None or not peers:
            continue
        benchmark = median(value for peer in peers if (value := _number(peer)) is not None)
        if benchmark <= 0 or number < QUARTER_FACTOR * benchmark:
            continue
        quarter = range(3 * ((month - 1) // 3) + 1, 3 * ((month - 1) // 3) + 4)
        if all(index in months and _number(months[index]) not in (None, 0) for index in quarter):
            continue
        issue = _issue(
            "data_quarter_in_month",
            f"Consum concentrat într-o lună: {name}, luna {MONTHS[month - 1]}.",
            field,
            next(
                (
                    months[index]
                    for index in quarter
                    if index != month and index in months and _number(months[index]) in (None, 0)
                ),
                peers[0],
            ),
        )
        if issue:
            result.append(issue)
    return result


def flags(fields: Mapping[str, Field]) -> list[Issue]:
    """Detect suspicions only when both compared source values have evidence."""
    result = _paired_flags(fields)
    for name, months in sorted(_series(fields).items()):
        result.extend(_monthly_flags(name, months))
    annual: dict[Carrier, list[tuple[int, Field]]] = {}
    for key, field in fields.items():
        parts = key.split(".")
        if len(parts) == 3 and parts[0] == "carrier" and parts[2].isdigit():
            carrier = _carrier(parts[1])
            if carrier is not None:
                annual.setdefault(carrier, []).append((int(parts[2]), field))
    for carrier, values in annual.items():
        ordered = sorted(values)
        for (earlier, before), (later, after) in pairwise(ordered):
            previous = Derived(
                _number(before), before.unit or "", "reading", (before.key,), year=earlier
            )
            current = Derived(_number(after), after.unit or "", "reading", (after.key,), year=later)
            reason = change_refusal(previous, current)
            if reason in {"bază zero", "ani neconsecutivi", "unități diferite"}:
                issue = _issue(
                    "data_change_refused",
                    f"Schimbare omisă: {CARRIER_NAMES_RO[carrier]}, {earlier}–{later}: {reason}.",
                    before,
                    after,
                )
                if issue:
                    result.append(issue)
    return result
