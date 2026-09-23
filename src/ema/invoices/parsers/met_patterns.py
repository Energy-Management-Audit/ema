from __future__ import annotations

import re

SUPPLIER_TAX_ID = "RO1877048"
INVOICE_NUMBER_PATTERN = re.compile(r"\b(?:EEFIN\d{2}|CV\d{2})\s+\d+\b", re.IGNORECASE)
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
FULL_PERIOD = re.compile(r"(?P<start>\d{4}-\d{2}-\d{2})\s*-\s*(?P<end>\d{4}-\d{2}-\d{2})")
MONTH_PERIOD = re.compile(r"(?P<start>\d{4}-\d{2})-\s*-\s*(?P<end>\d{4}-\d{2})-")
POD = re.compile(r"\bPOD\s*:\s*([A-Z0-9-]{8,})\b", re.IGNORECASE)
TAX_ID = re.compile(r"\bRO\s*\d{6,10}\b", re.IGNORECASE)
COMPANY = re.compile(r"[A-Z0-9][A-Z0-9 .&'’-]+\b(?:S\.?R\.?L\.?|S\.?A\.?)\b")
NUMBER = re.compile(r"[-−–]?[0-9][0-9.,]*")
VAT = re.compile(r"(?:0|5|9|19|21)(?:[.,]0+)?%?")
PRICE_UNITS = {"MWH", "KWH", "MAH", "MVARH", "KVARH", "H87"}
