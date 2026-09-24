from __future__ import annotations

import re

SUPPLIER_TAX_ID = "RO29156777"


NUMBER = r"[-−–]?[0-9][0-9.,]*"


AMOUNT = r"[-−–]?[0-9][0-9 ]*(?:[.,][0-9]+)?"


DATE = r"\d{2}[.\-/]\d{2}[.\-/]\d{4}"


TEXT_PRICE_ROW = re.compile(
    rf"^\s*\d+\s+(?P<description>.+?)\s+"
    rf"(?P<unit>MWh|kWh|kVArh|MVArh)\s+"
    rf"(?P<quantity>{NUMBER})\s+"
    rf"(?P<price>{NUMBER})\s+"
    rf"(?P<net>{AMOUNT})\s+"
    rf"(?P<vat>{AMOUNT})\s*$",
    re.IGNORECASE,
)


TEXT_ROW_CANDIDATE = re.compile(
    r"^\s*\d+\s+.+?\b(?:MWh|kWh|kVArh|MVArh)\b",
    re.IGNORECASE,
)


FULL_PERIOD = re.compile(rf"(?P<start>{DATE})\s*-\s*(?P<end>{DATE})")


MONTH_PERIOD = re.compile(
    r"perioada\s+(?:de\s+)?facturare\s*:\s*"
    r"(?P<month>ianuarie|februarie|martie|aprilie|mai|iunie|iulie|august|"
    r"septembrie|octombrie|noiembrie|decembrie)\s+(?P<year>\d{4})",
    re.IGNORECASE,
)


ROMANIAN_MONTHS = {
    "ianuarie": 1,
    "februarie": 2,
    "martie": 3,
    "aprilie": 4,
    "mai": 5,
    "iunie": 6,
    "iulie": 7,
    "august": 8,
    "septembrie": 9,
    "octombrie": 10,
    "noiembrie": 11,
    "decembrie": 12,
}


LOCATION = re.compile(r"\bAPM[A-Z0-9]{12,}\b", re.IGNORECASE)


TAX_ID = re.compile(r"RO\s*\d{6,10}(?!\d)", re.IGNORECASE)


LABELED_CLIENT = re.compile(
    r"client\s*:\s*(?P<value>[A-Z0-9][A-Z0-9 .&'’-]+?(?:S\.?R\.?L\.?|S\.?A\.?))\b",
    re.IGNORECASE,
)


COMPANY_LINE = re.compile(r"[A-Z0-9][A-Z0-9 .&'’-]{2,}(?:SRL|S\.R\.L\.|SA|S\.A\.)")
