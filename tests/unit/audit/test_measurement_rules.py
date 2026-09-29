"""Only confirmed, assessed values can receive a norm sentence."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from ema.audit.measurement_rules import assess
from ema.core.resources import resource_path
from ema.core.review.models import Field


def _field(quantity: str, phase: str, value: str, unit: str | None = None) -> Field:
    return Field(
        id=f"{quantity}-{phase}",
        job_id="synthetic",
        key=f"meter.panel.aaaaaaaa.{quantity}.{phase}",
        label=quantity,
        value_type="number",
        value=Decimal(value),
        unit=unit,
        state="extracted",
        presence="found",
        review="accepted",
    )


@pytest.mark.parametrize(
    ("quantity", "value", "unit", "rule", "status"),
    [
        ("voltage_ln", "230", "V", "voltage", "pass"),
        ("voltage_ln", "260", "V", "voltage", "fail"),
        ("voltage_ll", "0.4", "kV", "voltage", "pass"),
        ("voltage_ll", "0.5", "kV", "voltage", "fail"),
        ("frequency", "49.80", "Hz", "frequency", "pass"),
        ("frequency", "50.50", "Hz", "frequency", "fail"),
        ("thd_u", "8", "%", "thd_u", "pass"),
        ("thd_u", "8.1", "%", "thd_u", "fail"),
        ("power_factor", "0.9", None, "power_factor", "pass"),
        ("power_factor", "0.89", None, "power_factor", "fail"),
        ("thd_i", "3", "%", "thd_i", "unsupported"),
        ("power_active", "10", "kW", "power_active", "unsupported"),
    ],
)
def test_single_value_rules(
    quantity: str, value: str, unit: str | None, rule: str, status: str
) -> None:
    assert [(item.rule, item.status) for item in assess([_field(quantity, "l1", value, unit)])] == [
        (rule, status)
    ]


def test_current_asymmetry_and_pending() -> None:
    balanced = [
        _field("current", phase, value, "A")
        for phase, value in (("l1", "100"), ("l2", "101"), ("l3", "99"))
    ]
    assert assess(balanced)[0].status == "unsupported"
    unbalanced = [
        _field("current", phase, value, "A")
        for phase, value in (("l1", "100"), ("l2", "110"), ("l3", "90"))
    ]
    assert assess(unbalanced)[0].status == "unsupported"
    assert assess(balanced[:2])[0].status == "unsupported"
    assert assess([balanced[0].model_copy(update={"needs_confirmation": True})]) == []


def test_every_phrase_and_norm_has_traceable_source() -> None:
    with resource_path("audit", "measurement_phrases.json").open(encoding="utf-8") as handle:
        phrases = json.load(handle)
    with resource_path("audit", "measurement_norms.json").open(encoding="utf-8") as handle:
        norms = json.load(handle)
    assert all(item["id"] and item["template"] and " ¶ " in item["source"] for item in phrases)
    assert all(" ¶ " in item["source"] for item in norms.values())
