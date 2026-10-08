"""Official prices: band, VAT and density rules, the 25 % rule and the footnote."""

from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import pytest

from ema.energy_data.carriers import Carrier
from ema.energy_data.model import CarrierSeries, EnergyDataset, Reading
from ema.energy_data.prices import (
    band,
    bundled_prices,
    inferred_energy_costs,
    net_of_vat,
    per_tonne,
    read_prices,
    settle_cost,
    vat_rate,
)

FIXTURE = read_prices(
    Path(__file__).parents[2] / "fixtures" / "prices" / "energy_prices_fixture.json"
)


@pytest.mark.parametrize(
    ("mwh", "expected"),
    [
        (19.99, "IA"),
        (20, "IB"),
        (499.99, "IB"),
        (500, "IC"),
        (1_999.99, "IC"),
        (2_000, "ID"),
        (19_999.99, "ID"),
        (20_000, "IE"),
        (69_999.99, "IE"),
        (70_000, "IF"),
        (149_999.99, "IF"),
        (150_000, "IG"),
    ],
)
def test_electricity_band_at_each_boundary(mwh: float, expected: str) -> None:
    assert band(Carrier.electricity_grid, mwh) == expected


@pytest.mark.parametrize(
    ("gj", "expected"),
    [
        (999.99, "I1"),
        (1_000, "I2"),
        (9_999.99, "I2"),
        (10_000, "I3"),
        (99_999.99, "I3"),
        (100_000, "I4"),
        (999_999.99, "I4"),
        (1_000_000, "I5"),
        (3_999_999.99, "I5"),
        (4_000_000, "I6"),
    ],
)
def test_gas_band_at_each_boundary_in_gj(gj: float, expected: str) -> None:
    assert band(Carrier.natural_gas, gj / 3.6) == expected


def test_fuels_have_no_band() -> None:
    assert band(Carrier.diesel, 10) is None


def test_vat_switches_on_2025_08_01() -> None:
    assert vat_rate(date(2025, 7, 31)) == 0.19
    assert vat_rate(date(2025, 8, 1)) == 0.21
    assert net_of_vat(119, date(2025, 7, 31)) == pytest.approx(100)
    assert net_of_vat(121, date(2025, 8, 1)) == pytest.approx(100)


@pytest.mark.parametrize(
    ("carrier", "kg_per_litre"),
    [(Carrier.diesel, 0.84), (Carrier.petrol, 0.77), (Carrier.lpg, 0.54)],
)
def test_litre_price_to_tonne_uses_the_stated_density(
    carrier: Carrier, kg_per_litre: float
) -> None:
    assert per_tonne(6, carrier) == pytest.approx(6 / kg_per_litre * 1000)


def test_declared_cost_within_25_percent_is_kept() -> None:
    expected = 1_000 * 812.4
    settled = settle_cost(FIXTURE, Carrier.electricity_grid, 2024, 1_000, "MWh", expected * 1.24)
    assert settled.status == "declared"
    assert settled.cost == pytest.approx(expected * 1.24)
    assert settled.footnote is None


def test_declared_cost_beyond_25_percent_is_inferred() -> None:
    expected = 1_000 * 812.4
    for declared in (expected * 1.26, expected * 0.74):
        settled = settle_cost(FIXTURE, Carrier.electricity_grid, 2024, 1_000, "MWh", declared)
        assert settled.status == "inferred"
        assert settled.cost == pytest.approx(expected)


def test_missing_cost_is_inferred() -> None:
    settled = settle_cost(FIXTURE, Carrier.diesel, 2024, 10, "t", None)
    assert settled.status == "inferred"
    assert settled.cost == pytest.approx(72_805.3)


@pytest.mark.parametrize(
    ("carrier", "year", "unit"),
    [
        (Carrier.natural_gas, 2024, "Nm3"),
        (Carrier.purchased_heat, 2024, "Gcal"),
        (Carrier.diesel, 2022, "t"),
    ],
)
def test_unpriced_quantity_gives_no_cost(carrier: Carrier, year: int, unit: str) -> None:
    settled = settle_cost(FIXTURE, carrier, year, 100, unit, 5_000)
    assert settled.status == "unpriced"
    assert settled.expected is None
    assert settled.cost == 5_000


def test_band_without_a_row_is_unpriced() -> None:
    assert settle_cost(FIXTURE, Carrier.electricity_grid, 2024, 10, "MWh", None).status == (
        "unpriced"
    )


def test_footnote_verbatim() -> None:
    settled = settle_cost(FIXTURE, Carrier.electricity_grid, 2024, 1_068.47, "MWh", None)
    assert settled.footnote == (
        "Cost estimat: 1.068,47 MWh × 812,40 lei/MWh "
        "(Eurostat nrg_pc_205, 2024, consumatori non-casnici, fără TVA)."
    )


def test_bundled_table_rows_carry_their_source() -> None:
    rows = bundled_prices()
    for row in rows:
        assert row.source_name and row.source_url.startswith("https://")
        assert date.fromisoformat(row.retrieved) and row.vat_basis
    covered = {(row.carrier, row.year, row.band) for row in rows}
    for year in (2023, 2024, 2025):
        for code in ("IA", "IB", "IC", "ID", "IE", "IF", "IG"):
            assert (Carrier.electricity_grid, year, code) in covered
        for code in ("I1", "I2", "I3", "I4", "I5", "I6"):
            assert (Carrier.natural_gas, year, code) in covered
        for carrier in (Carrier.diesel, Carrier.petrol, Carrier.lpg):
            assert (carrier, year, None) in covered
    assert all("Legea 141/2025" in row.vat_basis for row in rows if row.unit == "t")


def _dataset(costs: dict[int, Reading], **carriers: CarrierSeries) -> EnergyDataset:
    return EnergyDataset(
        (2024,),
        {Carrier(name): {2024: series} for name, series in carriers.items()},
        energy_costs_lei=costs,
    )


def _annual(value: float, unit: str) -> CarrierSeries:
    return CarrierSeries(annual=Reading(value, unit))


def test_piee_total_is_replaced_by_the_sum_when_every_carrier_is_priced() -> None:
    dataset = _dataset(
        {2024: Reading(1_000, "lei")},
        electricity_grid=_annual(1_000, "MWh"),
        diesel=CarrierSeries({month: Reading(1, "t") for month in range(1, 13)}),
    )
    result, notes = inferred_energy_costs(dataset, FIXTURE)
    assert result.energy_costs_lei[2024].value == pytest.approx(1_000 * 812.4 + 12 * 7_280.53)
    assert notes[2024] == (
        "Cost estimat: 1.000,00 MWh × 812,40 lei/MWh "
        "(Eurostat nrg_pc_205, 2024, consumatori non-casnici, fără TVA).",
        "Cost estimat: 12,00 t × 7.280,53 lei/t (Comisia Europeană, Weekly Oil Bulletin, 2024, "
        "preț cu accize, fără TVA, curs mediu BNR 4,9746 lei/EUR, 0,84 kg/l).",
    )


def test_piee_total_within_25_percent_is_kept() -> None:
    dataset = _dataset({2024: Reading(900_000, "lei")}, electricity_grid=_annual(1_000, "MWh"))
    result, notes = inferred_energy_costs(dataset, FIXTURE)
    assert result is dataset
    assert notes == {}


def test_piee_total_stays_when_a_carrier_is_unpriced() -> None:
    for costs in ({2024: Reading(1, "lei")}, {}):
        dataset = _dataset(
            costs, electricity_grid=_annual(1_000, "MWh"), purchased_heat=_annual(50, "Gcal")
        )
        result, notes = inferred_energy_costs(dataset, FIXTURE)
        assert result.energy_costs_lei == costs
        assert notes == {}


def test_every_stored_url_is_one_openable_url() -> None:
    rows = bundled_prices()
    urls = [row.source_url for row in rows] + [
        row.fx_source_url for row in rows if row.fx_source_url
    ]
    for url in urls:
        parsed = urlparse(url)
        assert parsed.scheme == "https" and parsed.netloc, url
        assert not any(mark in url for mark in (" ", ";", ","))
    fuels = [row for row in rows if row.unit == "t"]
    assert fuels and all(row.fx_source_name and row.fx_source_url for row in fuels)
    assert all("bnr.ro" not in row.source_url for row in fuels)
