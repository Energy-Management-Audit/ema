"""Typed vision readouts and the closed meter vocabulary."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

type Quantity = Literal[
    "frequency",
    "voltage_ln",
    "voltage_ll",
    "current",
    "thd_u",
    "thd_i",
    "power_active",
    "power_reactive",
    "power_apparent",
    "power_factor",
    "energy_active",
    "energy_reactive",
]
type Phase = Literal["l1", "l2", "l3", "n", "l12", "l23", "l31", "total", "avg"]
type DisplayKind = Literal[
    "frequency",
    "voltage_ln",
    "voltage_ll",
    "current",
    "thd_u",
    "thd_i",
    "power",
    "power_factor",
    "energy",
    "overview",
]

UNITS: dict[str, frozenset[str | None]] = {
    "frequency": frozenset({"Hz"}),
    "voltage_ln": frozenset({"V", "kV"}),
    "voltage_ll": frozenset({"V", "kV"}),
    "current": frozenset({"A", "kA"}),
    "thd_u": frozenset({"%"}),
    "thd_i": frozenset({"%"}),
    "power_active": frozenset({"W", "kW", "MW"}),
    "power_reactive": frozenset({"var", "kvar", "Mvar"}),
    "power_apparent": frozenset({"VA", "kVA", "MVA"}),
    "power_factor": frozenset({None}),
    "energy_active": frozenset({"Wh", "kWh", "MWh"}),
    "energy_reactive": frozenset({"varh", "kvarh", "Mvarh"}),
}


class DisplayValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: Quantity
    phase: Phase
    value: str
    unit: str | None
    region: tuple[float, float, float, float] | None


class MeterReadout(BaseModel):
    model_config = ConfigDict(extra="forbid")

    readable: bool
    display: DisplayKind | None
    device: str | None
    values: list[DisplayValue]
    unreadable_reason: str | None


class ThermalReadout(BaseModel):
    model_config = ConfigDict(extra="forbid")

    readable: bool
    component: str | None
    spot: str | None
    max: str | None
    min: str | None
    unreadable_reason: str | None
