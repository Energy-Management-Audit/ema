"""Non-blocking, source-backed suspicions in audit review fields."""

from __future__ import annotations

from collections.abc import Mapping
from itertools import pairwise
from statistics import median

from ema.audit.chapter_four_sentences import change_refusal
from ema.core.review.models import Field, Issue
from ema.energy_data.model import Derived

QUARTER_FACTOR = 2.5


def _number(field: Field | None) -> float | None:
    if field is None or field.value is None or field.value_type != "number":
        return None
    return float(field.value)


def _issue(code: str, message: str, *fields: Field) -> Issue | None:
    evidence = tuple(dict.fromkeys(ref for field in fields for ref in field.evidence))
    if len(evidence) < 2:
        return None
    return Issue(code=code, field_id=fields[0].id, message=message, evidence_ids=evidence)


def _paired_flags(fields: Mapping[str, Field]) -> list[Issue]:
    result: list[Issue] = []
    for key, field in sorted(fields.items()):
        if key.startswith("carrier.lpg.") and key.count(".") == 2 and _number(field) == 0:
            year = key.rsplit(".", 1)[1]
            cost = fields.get(f"audit.economics.lpg_costs_lei.{year}")
            if cost is not None and (_number(cost) or 0) > 0:
                issue = _issue(
                    "data_gpl_cost_no_quantity",
                    f"GPL: cost pozitiv şi cantitate zero în {year}.",
                    field,
                    cost,
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
    result: dict[str, dict[int, Field]] = {}
    for key, field in fields.items():
        parts = key.split(".")
        if (
            len(parts) != 4
            or parts[0] != "carrier"
            or not all(part.isdigit() for part in parts[2:])
        ):
            continue
        month = int(parts[3])
        if 1 <= month <= 12:
            result.setdefault(".".join(parts[:3]), {})[month] = field
    return result


def _monthly_flags(name: str, months: dict[int, Field]) -> list[Issue]:
    result: list[Issue] = []
    for month in range(1, 12):
        first, second = months.get(month), months.get(month + 1)
        if first is None or second is None or _number(first) is None:
            continue
        if _number(first) == _number(second):
            issue = _issue(
                "data_month_repeat",
                f"Luni consecutive egale: {name}, {month} şi {month + 1}.",
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
            f"Consum concentrat într-o lună: {name}, luna {month}.",
            field,
            peers[0],
        )
        if issue:
            result.append(issue)
    return result


def flags(fields: Mapping[str, Field]) -> list[Issue]:
    """Detect suspicions only when both compared source values have evidence."""
    result = _paired_flags(fields)
    for name, months in sorted(_series(fields).items()):
        result.extend(_monthly_flags(name, months))
    annual: dict[str, list[tuple[int, Field]]] = {}
    for key, field in fields.items():
        parts = key.split(".")
        if len(parts) == 3 and parts[0] == "carrier" and parts[2].isdigit():
            annual.setdefault(parts[1], []).append((int(parts[2]), field))
    for carrier, values in annual.items():
        ordered = sorted(values)
        for (earlier, before), (later, after) in pairwise(ordered):
            if before.unit != after.unit:
                continue
            previous = Derived(
                _number(before), before.unit or "", "reading", (before.key,), year=earlier
            )
            current = Derived(_number(after), after.unit or "", "reading", (after.key,), year=later)
            reason = change_refusal(previous, current)
            if reason in {"bază zero", "ani neconsecutivi"}:
                issue = _issue(
                    "data_change_refused",
                    f"Schimbare omisă: {carrier}, {earlier}–{later}: {reason}.",
                    before,
                    after,
                )
                if issue:
                    result.append(issue)
    return result
