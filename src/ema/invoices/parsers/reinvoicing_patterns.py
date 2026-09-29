from __future__ import annotations

import re
from dataclasses import dataclass

from ema.invoices.models import DocumentPage

DATE = r"\d{2}\.\d{2}\.\d{4}"


NUMBER = r"[-−–]?[0-9](?:[0-9.,]*[0-9])?[.]?"


GETICA_ROW = re.compile(
    rf"^\s*(?P<row>\d+)\s+(?P<description>.+?)\s+"
    rf"(?P<unit>MWh|kWh|kVArh|MVArh)\s+"
    rf"(?P<quantity>{NUMBER})\s+(?P<price>{NUMBER})\s+"
    rf"(?P<net>{NUMBER})\s+(?P<vat>{NUMBER})(?:\s+.*)?$",
    re.IGNORECASE,
)


GETICA_SPLIT_ROW = re.compile(
    rf"^\s*(?P<row>\d+)\s+"
    rf"(?P<unit>MWh|kWh|kVArh|MVArh)\s+"
    rf"(?P<quantity>{NUMBER})\s+(?P<price>{NUMBER})\s+"
    rf"(?P<net>{NUMBER})\s+(?P<vat>{NUMBER})(?:\s+.*)?$",
    re.IGNORECASE,
)


ELECTRIC_ROW = re.compile(
    rf"^\s*(?P<description>.+?)\s+"
    rf"(?P<unit>MWh|kWh|kVArh|MVArh)\s+"
    rf"(?P<quantity>{NUMBER})\s+(?P<price>{NUMBER})\s+"
    rf"(?P<net>{NUMBER})\s+(?P<vat>{NUMBER})\s+(?P<total>{NUMBER})\s*$",
    re.IGNORECASE,
)


POD = re.compile(r"\bPOD\s*:\s*(?P<value>[0-9]{12,})", re.IGNORECASE)


ELECTRIC_POD = re.compile(
    r"Cod de identificare loc de consum \(POD\):\s*(?P<value>[0-9]{12,})",
    re.IGNORECASE,
)


METER = re.compile(r"Serie contor:\s*(?P<value>[#A-Z0-9./_-]+)", re.IGNORECASE)


CONSUMPTION_PERIOD_PATTERN = re.compile(
    rf"Energie\s+(?:activ[aă]|reactiv[aă])[^\r\n]*?" rf"(?P<start>{DATE})\s*-\s*(?P<end>{DATE})",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Segment:
    pod: str
    meter: str | None
    period: str | None
    page: DocumentPage
