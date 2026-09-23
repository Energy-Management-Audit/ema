from __future__ import annotations

import re

DATE_PATTERN = r"\d{2}\.\d{2}\.\d{4}"
# PyMuPDF can append one token from the vertical "Pagina 6 din 8" footer to a
# bottom table row. Accept only those known footer fragments after the five
# financial columns so unrelated trailing content still invalidates the row.
ROW_PATTERN = re.compile(
    r"^\s*(?:(?P<unit>kWh|MWh|kVArh)\s+)?"
    r"(?P<description>.+?)\s+"
    r"(?P<quantity>-?[0-9][0-9.]*,[0-9]+)\s+"
    r"(?P<price>-?[0-9][0-9.]*,[0-9]+)\s+"
    r"(?P<net>-?[0-9][0-9.]*,[0-9]+)\s+"
    r"(?P<vat>-?[0-9][0-9.]*,[0-9]+)\s+"
    r"(?P<total>-?[0-9][0-9.]*,[0-9]+)"
    r"(?:\s+(?:pagina|din|factura|anexa|nr\.?|la|\d+))?\s*$",
    re.IGNORECASE,
)
REACTIVE_METER_READING = re.compile(
    r"energie\s+reactiva\s+(?P<kind>capacitiva|inductiva)\s+masurata.*?"
    r"(?P<quantity>[0-9][0-9.]*)\s*$",
    re.IGNORECASE,
)
