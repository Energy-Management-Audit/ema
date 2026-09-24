"""Read ALIVE's scanned invoice headings and consumption period."""

from __future__ import annotations

import re
from calendar import monthrange
from collections import Counter
from datetime import date

from ema.invoices.models import InputDocument, SourceEvidence
from ema.invoices.parsers.engie_text import plain_text
from ema.invoices.parsers.identity_fields import first_match
from ema.invoices.parsers.normalization import parse_romanian_date

MONTHS = {
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
MONTH_RANGE = re.compile(
    r"\b(?P<start>\d{1,2})\s*-\s*(?P<end>\d{1,2})\s+"
    r"(?P<month>" + "|".join(MONTHS) + r")\s+(?P<year>\d{4})\b",
    re.I,
)
NUMERIC_RANGE = re.compile(
    r"\b(?P<start>\d{2}[./-]\d{2}[./-]\d{4})\s*-\s*" r"(?P<end>\d{2}[./-]\d{2}[./-]\d{4})\b"
)
POD = re.compile(
    r"\b(?:POD|cod\s+loc(?:\s+de)?\s+consum|cod\s+autocitire|instalatie)"
    r"\s*:?\s*([A-Z0-9-]{6,})\b",
    re.I,
)
NUMBER = re.compile(r"\b(?P<year>\d{2})\s*FE\s*(?P<number>\d{3,7})\b", re.I)
PREFERRED_NUMBER = re.compile(
    r"^\s*(?:(?:invoice\s+number|n[°o.]?)\s*[:,.]?\s*)?"
    r"(?P<year>\d{2})\s*FE\s*(?P<number>\d{3,7})\s*(?:RO)?\s*$",
    re.I,
)
POSITION_COUNT = re.compile(r"\bnr\.?\s+pozit(?:ii|i[iî])\s+fact\.?\s*[:.]?\s*(\d{1,2})", re.I)


def invoice_positions(document: InputDocument) -> tuple[int | None, tuple[SourceEvidence, ...]]:
    for page in document.pages:
        for line in page.text.splitlines():
            if match := POSITION_COUNT.search(plain_text(line)):
                return int(match[1]), (
                    SourceEvidence(page.number, line.strip(), "invoice positions"),
                )
    return None, ()


def invoice_number(document: InputDocument) -> tuple[str | None, tuple[SourceEvidence, ...]]:
    for page in document.pages:
        for line in page.text.splitlines():
            if match := PREFERRED_NUMBER.match(line):
                return f"{match['year']}FE{match['number']}", (
                    SourceEvidence(page.number, line.strip(), "invoice number"),
                )
    annex = re.compile(r"anexa\s+la\s+factura\s+(\d{2})\s*FE\s*(\d{3,7})", re.I)
    found = first_match(document, annex, lambda m: f"{m[1]}FE{m[2]}", "invoice metadata")
    return (
        found
        if found[0]
        else first_match(
            document, NUMBER, lambda m: f"{m['year']}FE{m['number']}", "invoice metadata"
        )
    )


def invoice_date(document: InputDocument) -> tuple[date | None, tuple[SourceEvidence, ...]]:
    patterns = (
        re.compile(r"data\s+emiter\w*\s*[:.]?\s*(\d{2}[./-]\d{2}[./-]\d{4})", re.I),
        re.compile(
            r"(?:document\s+date|invoice\s+date)\s*:?\s*(\d{2}[./-]\d{2}[./-]\d{4}|\d{4}-\d{2}-\d{2})",
            re.I,
        ),
        re.compile(
            r"anexa\s+la\s+factura\s+\d{2}\s*FE\s*\d{3,7}\s*/\s*(\d{2}[./-]\d{2}[./-]\d{4})", re.I
        ),
    )
    for pattern in patterns:
        value, evidence = first_match(
            document,
            pattern,
            lambda m: (
                date.fromisoformat(m[1])
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", m[1])
                else parse_romanian_date(m[1])
            ),
            "invoice metadata",
        )
        if value:
            return value, evidence
    return None, ()


def locations(document: InputDocument) -> list[tuple[str, tuple[SourceEvidence, ...]]]:
    found: dict[str, list[SourceEvidence]] = {}
    for page in document.pages:
        for match in POD.finditer(page.text):
            identifier = re.sub(r"[^A-Z0-9]", "", match[1].upper())
            found.setdefault(identifier, []).append(
                SourceEvidence(page.number, match.group(0), "consumption location")
            )
    return [(key, tuple(value)) for key, value in found.items()]


def billing_period(document: InputDocument) -> tuple[str | None, tuple[SourceEvidence, ...]]:
    candidates: list[tuple[date, date, SourceEvidence]] = []
    for page in document.pages:
        for match in MONTH_RANGE.finditer(plain_text(page.text)):
            try:
                start = date(int(match["year"]), MONTHS[match["month"]], int(match["start"]))
                end = date(int(match["year"]), MONTHS[match["month"]], int(match["end"]))
            except ValueError:
                continue
            candidates.append(
                (start, end, SourceEvidence(page.number, match.group(0), "billing period"))
            )
        for match in NUMERIC_RANGE.finditer(page.text):
            try:
                start, end = parse_romanian_date(match["start"]), parse_romanian_date(match["end"])
            except ValueError:
                continue
            candidates.append(
                (start, end, SourceEvidence(page.number, match.group(0), "billing period"))
            )
    if not candidates:
        return None, ()
    counts = Counter((start, end) for start, end, _ in candidates)
    maximum = max(counts.values())
    full_month = [
        (period, count)
        for period, count in counts.items()
        if period[0].day == 1
        and period[0].year == period[1].year
        and period[0].month == period[1].month
        and period[1].day == monthrange(period[1].year, period[1].month)[1]
    ]
    preferred = max(full_month, key=lambda item: item[1]) if full_month else None
    if preferred and preferred[1] >= 2 and maximum <= preferred[1] + 1:
        ranges = [preferred[0]]
    else:
        ranges = [period for period, count in counts.items() if count == maximum]
    start, end = (
        ranges[0]
        if len(ranges) == 1
        else (min(item[0] for item in candidates), max(item[1] for item in candidates))
    )
    evidence = tuple(item[2] for item in candidates if item[:2] == (start, end))
    return f"{start:%d.%m.%Y} - {end:%d.%m.%Y}", evidence
