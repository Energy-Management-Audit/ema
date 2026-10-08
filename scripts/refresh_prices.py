"""Rebuild resources/prices/energy_prices_ro.json from the official sources.

Run by hand (network): `uv run python scripts/refresh_prices.py [--years 2023 2024 2025]`.
Never run in CI; tests use a small fixture table.

- Electricity and natural gas: Eurostat nrg_pc_205 / nrg_pc_203, RO, non-household, excluding
  VAT and recoverable taxes, in RON; the annual price is the mean of the two semesters.
- Diesel, petrol and LPG: the European Commission Weekly Oil Bulletin history, RO, prices with
  taxes in EUR/1000 l. VAT is removed week by week, the yearly mean is converted with the BNR
  annual mean EUR/RON and then to lei/t through the stated densities.
"""

from __future__ import annotations

import argparse
import io
import json
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path
from statistics import fmean
from typing import Any

import httpx
import openpyxl

from ema.core.office.numbers_ro import format_number
from ema.core.resources import resource_path
from ema.energy_data.carriers import Carrier
from ema.energy_data.prices import KG_PER_LITRE, net_of_vat, per_tonne

EUROSTAT = (
    "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{code}"
    "?format=JSON&lang=EN&geo=RO&currency=NAC&tax=X_VAT&unit=KWH&nrg_cons={cons}"
    "&sinceTimePeriod={first}-S1&untilTimePeriod={last}-S2"
)
WOB = (
    "https://energy.ec.europa.eu/document/download/906e60ca-8b6a-44e7-8589-652854d2fd3f_en"
    "?filename=Weekly_Oil_Bulletin_Prices_History_maticni_4web.xlsx"
)
BNR = "https://curs.bnr.ro/files/xml/years/nbrfxrates{year}.xml"
EUROSTAT_BANDS = {
    "nrg_pc_205": (
        Carrier.electricity_grid,
        {
            "IA": "MWH_LT20",
            "IB": "MWH20-499",
            "IC": "MWH500-1999",
            "ID": "MWH2000-19999",
            "IE": "MWH20000-69999",
            "IF": "MWH70000-149999",
            "IG": "MWH_GE150000",
        },
    ),
    "nrg_pc_203": (
        Carrier.natural_gas,
        {
            "I1": "GJ_LT1000",
            "I2": "GJ1000-9999",
            "I3": "GJ10000-99999",
            "I4": "GJ100000-999999",
            "I5": "GJ1000000-3999999",
            "I6": "GJ_GE4000000",
        },
    ),
}
WOB_COLUMNS = {
    Carrier.diesel: "RO_price_with_tax_diesel",
    Carrier.petrol: "RO_price_with_tax_euro95",
    Carrier.lpg: "RO_price_with_tax_LPG",
}
EUROSTAT_VAT = "fără TVA și alte taxe recuperabile (Eurostat tax=X_VAT)"
WOB_VAT = (
    "preț cu taxe, din care TVA scăzut săptămână de săptămână: 19 % până la 2025-07-31, "
    "21 % de la 2025-08-01 (Legea 141/2025)"
)


def _get(url: str) -> bytes:
    response = httpx.get(url, follow_redirects=True, timeout=120)
    response.raise_for_status()
    return response.content


def _eurostat(code: str, years: list[int], retrieved: str) -> list[dict[str, Any]]:
    carrier, bands = EUROSTAT_BANDS[code]
    rows: list[dict[str, Any]] = []
    for band, cons in bands.items():
        url = EUROSTAT.format(code=code, cons=cons, first=years[0], last=years[-1])
        data = json.loads(_get(url))
        times = data["dimension"]["time"]["category"]["index"]
        values = {str(key): float(value) for key, value in data["value"].items()}
        for year in years:
            semesters = [values.get(str(times[f"{year}-S{half}"])) for half in (1, 2)]
            if any(value is None for value in semesters):
                print(f"skip {code} {band} {year}: semester missing")
                continue
            rows.append(
                {
                    "carrier": carrier.value,
                    "year": year,
                    "band": band,
                    "value": round(fmean(v for v in semesters if v is not None) * 1000, 2),
                    "unit": "MWh",
                    "note": "consumatori non-casnici, fără TVA",
                    "vat_basis": EUROSTAT_VAT,
                    "source_name": f"Eurostat {code}",
                    "source_url": url,
                    "retrieved": retrieved,
                }
            )
    return rows


def _bnr_mean(year: int) -> float:
    root = ET.fromstring(_get(BNR.format(year=year)))
    rates = [
        float(rate.text or "")
        for rate in root.iter("{http://www.bnr.ro/xsd}Rate")
        if rate.get("currency") == "EUR"
    ]
    return fmean(rates)


def _weekly_oil(years: list[int], retrieved: str) -> list[dict[str, Any]]:
    book = openpyxl.load_workbook(io.BytesIO(_get(WOB)), read_only=True, data_only=True)
    sheet = book["Prices with taxes"]
    table = list(sheet.iter_rows(values_only=True))
    header = [str(cell) if cell is not None else "" for cell in table[0]]
    rows: list[dict[str, Any]] = []
    for year in years:
        rate = _bnr_mean(year)
        for carrier, column in WOB_COLUMNS.items():
            index = header.index(column)
            weekly = [
                net_of_vat(float(line[index]), line[0].date())
                for line in table[3:]
                if isinstance(line[0], datetime)
                and line[0].year == year
                and isinstance(line[index], int | float)
            ]
            if not weekly:
                print(f"skip {carrier.value} {year}: no weekly prices")
                continue
            lei_per_litre = fmean(weekly) / 1000 * rate
            density = format_number(KG_PER_LITRE[carrier], 2)
            rows.append(
                {
                    "carrier": carrier.value,
                    "year": year,
                    "band": None,
                    "value": round(per_tonne(lei_per_litre, carrier), 2),
                    "unit": "t",
                    "note": (
                        f"preț cu accize, fără TVA, curs mediu BNR "
                        f"{format_number(rate, 4)} lei/EUR, {density} kg/l"
                    ),
                    "vat_basis": WOB_VAT,
                    "source_name": "Comisia Europeană, Weekly Oil Bulletin",
                    "source_url": WOB,
                    "fx_source_name": "BNR, curs mediu anual EUR/RON",
                    "fx_source_url": BNR.format(year=year),
                    "retrieved": retrieved,
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--years", nargs="+", type=int, default=[2023, 2024, 2025])
    parser.add_argument(
        "--out", type=Path, default=resource_path("prices", "energy_prices_ro.json")
    )
    args = parser.parse_args()
    years = sorted(args.years)
    retrieved = date.today().isoformat()
    rows = [
        *_eurostat("nrg_pc_205", years, retrieved),
        *_eurostat("nrg_pc_203", years, retrieved),
        *_weekly_oil(years, retrieved),
    ]
    rows.sort(key=lambda row: (row["carrier"], row["year"], row["band"] or ""))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({"rows": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{len(rows)} rows -> {args.out}")


if __name__ == "__main__":
    main()
