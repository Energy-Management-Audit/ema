from __future__ import annotations

import re
from dataclasses import dataclass

from ema.invoices.models import DocumentPage, PriceDetail

NUMBER = r"[-−–]?[0-9](?:[0-9.,]*[0-9])?"


SHORT_DATE = r"\d{2}[.]\d{2}[.]\d{2,4}"


PERIOD = re.compile(
    rf"(?P<start>{SHORT_DATE})\s*-\s*(?P<end>{SHORT_DATE})",
    re.IGNORECASE,
)


INVOICE = re.compile(
    r"(?:Factur[ăa]\s+fiscal[ăa]|Anex[ăa]\s+la\s+factura)\s+seria\s+"
    r"(?P<series>FX|\d{2}EI)\s+nr[.]?\s*(?P<number>[0-9]+)\s+"
    r"din\s+data\s+de\s+(?P<date>\d{2}[.]\d{2}[.]\d{4})",
    re.IGNORECASE,
)


BILLING_PERIOD_PATTERN = re.compile(
    rf"Perioad[ăa]\s+de\s+facturare:\s*(?P<start>{SHORT_DATE})\s*-\s*" rf"(?P<end>{SHORT_DATE})",
    re.IGNORECASE,
)


HYDRO_LOCATION = re.compile(
    r"POD\s+_+\s*(?P<pod>[A-Z0-9]{8,})",
    re.IGNORECASE,
)


HYDRO_FALLBACK_LOCATION = re.compile(
    r"Denumire\s+loc\s+de\s+consum\s*[_ ]+(?P<pod>[A-Z0-9]{8,})",
    re.IGNORECASE,
)


PPC_LOCATION = re.compile(
    r"Cod\s+punct\s+de\s+m[ăa]sur[ăa]\s+(?P<pod>[A-Z0-9]{8,})",
    re.IGNORECASE,
)


PPC_FALLBACK_LOCATION = re.compile(
    r"cod\s+loc\s+consum\s+(?P<pod>[A-Z0-9]{8,})",
    re.IGNORECASE,
)


LOCATION_ADDRESS = re.compile(
    r"Adres[ăa]\s+loc\s+(?:de\s+)?consum\s+(?P<value>[^\r\n]+)",
    re.IGNORECASE,
)


PPC_METER = re.compile(r"Serie\s+contor:\s*(?P<value>[#A-Z0-9./_-]+)", re.IGNORECASE)


METER_EA = re.compile(r"(?P<meter>#{0,2}[0-9]{5,})\s+EA\s+kWh\b", re.IGNORECASE)


CLIENT_NAME_PATTERN = re.compile(
    r"\bClient\s*:\s*(?P<value>[^\r\n]+)",
    re.IGNORECASE,
)


CLIENT_TAX = re.compile(
    r"\b(?:CIF|Cod\s+fiscal)\s*:\s*(?P<value>RO\s*[0-9]{2,10}|[0-9]{2,10})",
    re.IGNORECASE,
)


ROW_PERIOD_FIRST = re.compile(
    rf"^\s*(?P<description>.*?)\s*(?P<start>{SHORT_DATE})\s*-\s*"
    rf"(?P<end>{SHORT_DATE})\s+(?P<quantity>{NUMBER})\s+"
    rf"(?P<unit>MWh|kWh|kVArh|MVArh)\s+(?P<price>{NUMBER})\s+"
    rf"(?P<net>{NUMBER})(?:\s+{NUMBER})?(?:\s+{NUMBER})?\s*$",
    re.IGNORECASE,
)


ROW_PERIOD_LAST = re.compile(
    rf"^\s*(?P<description>.+?)\s+(?P<quantity>{NUMBER})\s+"
    rf"(?P<unit>MWh|kWh|kVArh|MVArh|Buc)\s+(?P<price>{NUMBER})\s+"
    rf"(?P<net>{NUMBER})(?:\s+{NUMBER})?(?:\s+{NUMBER})?"
    rf"(?:\s+(?P<start>{SHORT_DATE})\s*-\s*(?P<end>{SHORT_DATE}))?\s*$",
    re.IGNORECASE,
)


ROW_NO_PERIOD = re.compile(
    rf"^\s*(?P<description>.+?)\s+(?P<quantity>{NUMBER})\s+"
    rf"(?P<unit>MWh|kWh|kVArh|MVArh|Buc)\s+(?P<price>{NUMBER})\s+"
    rf"(?P<net>{NUMBER})(?:\s+{NUMBER})?(?:\s+{NUMBER})?"
    r"(?:\s+[A-Za-zĂÂÎȘȚăâîșț]+)*\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedRow:
    detail: PriceDetail
    period: str | None


@dataclass(frozen=True)
class LocationSegment:
    pod: str | None
    name: str | None
    pages: tuple[DocumentPage, ...]
