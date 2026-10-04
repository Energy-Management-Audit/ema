"""PIEE identity text uses only supplied annex values and safe website targets."""

from datetime import date

import pytest

from ema.core.office.sheets import CellRef
from ema.energy_data.anexa_cells import AnexaData
from ema.energy_data.source import Located
from ema.piee.identity import identity_values, website_target


def _located(value: str) -> Located:
    return Located(value, CellRef("Anexa", 1, 1))


@pytest.mark.parametrize(
    "url",
    [
        "https://user:pass@example.com",
        "javascript://example.com",
        "https://bad_host.test",
        "localhost",
    ],
)
def test_unsafe_website_is_not_emitted(url: str) -> None:
    anexa = AnexaData(identity={"website": _located(url)})
    assert website_target(anexa) is None


def test_identity_values_include_sourced_address_and_contact() -> None:
    anexa = AnexaData(
        identity={
            "name": _located("Synthetic Company"),
            "address": _located("Strada Test nr. 12, 123456, Oraș Test, jud. Test"),
            "cui": _located("RO 12345678"),
            "ownership_state": _located("0%"),
            "ownership_private": _located("100,00 %"),
            "phone": _located("0712345678"),
            "website": _located("example.test"),
            "caen_code": _located("1000"),
            "caen_description": _located("production"),
        }
    )
    values = identity_values(anexa, date(2026, 1, 2), production_name="synthetic product")
    assert values["client_name"] == "Synthetic Company"
    assert values["footer_address"] == "12 Strada Test, 123456 Oraș Test, Test County"
    assert values["cui"] == "12345678"
    assert values["ownership"] == "Companie cu capital integral privat: 100,00% capital privat."
    assert values["phone"] == "0712 345 678"
    assert values["website_target"] == "https://example.test"
    assert values["caen"] == "1000: production"
    assert values["generation_date"] == "02.01.2026"
    assert values["production_name"] == "synthetic product"


def test_incomplete_address_stays_missing() -> None:
    values = identity_values(
        AnexaData(identity={"address": _located("Strada Test, Oraș Test")}), date(2026, 1, 2)
    )
    assert values["footer_address"] is None


@pytest.mark.parametrize("raw", ["0", "1", "DA", "<label>", "Privat", "Stat", "20% text"])
def test_non_percentage_ownership_is_missing(raw: str) -> None:
    anexa = AnexaData(
        identity={
            "ownership_state": _located(raw),
            "ownership_private": _located("100%"),
        }
    )
    assert identity_values(anexa, date(2026, 1, 2))["ownership"] == (
        "Companie cu capital integral privat: 100% capital privat."
    )
