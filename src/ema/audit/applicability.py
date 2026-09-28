"""Three-valued applicability over audit facts and material records."""

from __future__ import annotations

from ema.audit.catalogue import AuditFact, CarrierPattern, Condition
from ema.audit.catalogue_types import PrefixPattern
from ema.core.review.models import Field
from ema.energy_data.carriers import Carrier
from ema.energy_data.model import field_key


def carrier_fields(pattern: CarrierPattern, facts: dict[str, Field]) -> list[Field]:
    result: list[Field] = []
    allowed = set(pattern.carriers or tuple(Carrier))
    for key, field in facts.items():
        parts = key.split(".")
        if len(parts) not in (3, 4) or parts[0] != "carrier" or parts[1] not in allowed:
            continue
        try:
            year = int(parts[2])
            month = int(parts[3]) if len(parts) == 4 else None
            if field_key("carrier", parts[1], year, month) == key:
                result.append(field)
        except ValueError:
            continue
    return result


def fact_fields(
    ref: AuditFact | CarrierPattern | PrefixPattern, facts: dict[str, Field]
) -> list[Field]:
    if isinstance(ref, AuditFact):
        field = facts.get(ref.value)
        return [field] if field is not None else []
    if isinstance(ref, PrefixPattern):
        return [field for key, field in sorted(facts.items()) if key.startswith(ref.prefix)]
    return carrier_fields(ref, facts)


def applies(  # noqa: PLR0911
    condition: Condition, materials: dict[str, bool], facts: dict[str, Field]
) -> bool | None:
    if condition.op == "always":
        return True
    if condition.op == "material":
        return materials.get(condition.key)
    if condition.op == "fact":
        field = facts.get(condition.key)
        return None if field is None or field.presence == "failed" else field.presence == "found"
    if condition.op == "carrier":
        matches = carrier_fields(CarrierPattern(condition.carriers), facts)
        if not matches:
            return None
        if any(field.presence == "found" for field in matches):
            return True
        return None if any(field.presence == "failed" for field in matches) else False
    values = [applies(child, materials, facts) for child in condition.children]
    if condition.op == "any":
        return True if True in values else None if None in values else False
    return False if False in values else None if None in values else True


def condition_source(condition: Condition) -> str:
    """The condition as recorded in a section's applicability reason."""
    if condition.op == "carrier":
        return "carrier:" + ",".join(carrier.value for carrier in condition.carriers)
    if condition.children:
        return (
            condition.op
            + "("
            + ",".join(condition_source(child) for child in condition.children)
            + ")"
        )
    return condition.op + (":" + condition.key if condition.key else "")
