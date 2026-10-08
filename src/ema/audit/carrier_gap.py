"""The review message for a used carrier with incomplete quantity."""

from __future__ import annotations

from ema.energy_data.carriers import CARRIER_NAMES_RO, Carrier


def blocked_message(carrier: Carrier, year: int) -> str:
    name = CARRIER_NAMES_RO[carrier]
    return f"Totalul de energie din {year} lipseşte: completaţi cantitatea de {name}."
