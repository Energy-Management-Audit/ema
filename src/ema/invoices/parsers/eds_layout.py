from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise

from ema.invoices.models import DocumentPage, InputDocument
from ema.invoices.parsers.eds_text import normalized_ocr_text

DATE = r"\d{2}\.\d{2}\.\d{4}"

_POD = re.compile(
    r"Cod de identificare loc de consum \(POD\):\s*(?P<value>[0-9]+)",
    re.IGNORECASE,
)
_LOCATION_NAME = re.compile(r"Denumire loc de consum:\s*(?P<value>[^\r\n]+)", re.IGNORECASE)
_METER_IDENTIFIER = re.compile(
    r"Serie contor[:;]\s*(?P<value>[#A-Z0-9./_-]+)",
    re.IGNORECASE,
)
_CONSUMPTION_PERIOD = re.compile(
    rf"Energie[^\r\n]*?\s+(?P<start>{DATE})\s*-\s*(?P<end>{DATE})",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _ConsumptionSegment:
    identifier: str
    name: str | None
    meter_identifier: str | None
    meter_source_value: str | None
    consumption_period: str | None
    pages: tuple[DocumentPage, ...]
    ambiguous_locations: bool = False


def consumption_segments(
    document: InputDocument,
    billing_period: str | None,
) -> tuple[_ConsumptionSegment, ...]:
    grouped_pages: dict[tuple[str, str, str], list[DocumentPage]] = {}
    attributes: dict[
        tuple[str, str, str],
        tuple[str | None, str | None, str | None, str | None],
    ] = {}
    ambiguous_keys: set[tuple[str, str, str]] = set()
    for original_page in document.pages:
        sections, ambiguous = _page_sections(original_page)
        for page in sections:
            text = normalized_ocr_text(page.text)
            pod = _POD.search(text)
            if pod is None:
                continue
            identifier = pod.group("value")
            name = _LOCATION_NAME.search(text)
            meter = _METER_IDENTIFIER.search(text)
            period = _CONSUMPTION_PERIOD.search(text)
            meter_source_value = meter.group("value").strip() if meter else None
            meter_identifier = _normalize_meter_identifier(meter_source_value)
            consumption_period = (
                f"{period.group('start')} - {period.group('end')}"
                if period
                else (billing_period if meter else None)
            )
            # Missing identifiers remain distinct and review-blocking.
            meter_key = meter_identifier or f"page-{page.number}"
            period_key = consumption_period or f"page-{page.number}"
            key = (identifier, meter_key, period_key)
            grouped_pages.setdefault(key, []).append(page)
            attributes.setdefault(
                key,
                (
                    name.group("value").strip() if name else None,
                    meter_identifier,
                    meter_source_value,
                    consumption_period,
                ),
            )
            if ambiguous:
                ambiguous_keys.add(key)
    return tuple(
        _ConsumptionSegment(
            identifier=key[0],
            name=attributes[key][0],
            meter_identifier=attributes[key][1],
            meter_source_value=attributes[key][2],
            consumption_period=attributes[key][3],
            pages=tuple(pages),
            ambiguous_locations=key in ambiguous_keys,
        )
        for key, pages in grouped_pages.items()
    )


def _page_sections(page: DocumentPage) -> tuple[tuple[DocumentPage, ...], bool]:
    text = normalized_ocr_text(page.text)
    pods = list(_POD.finditer(text))
    if len(pods) < 2:
        return (page,), False
    names = list(_LOCATION_NAME.finditer(text))
    ordered = len(names) == len(pods) and all(
        names[index].start()
        < pod.start()
        < (names[index + 1].start() if index + 1 < len(names) else len(text))
        for index, pod in enumerate(pods)
    )
    if not ordered:
        return (page,), True
    boundaries = [0, *(name.start() for name in names[1:]), len(text)]
    sections = tuple(
        DocumentPage(page.number, text[start:end], page.blocks, page.extraction_method)
        for start, end in pairwise(boundaries)
    )
    if any(
        not re.search(r"\b(?:MWh|kWh|kVArh|MVArh)\b", section.text, re.IGNORECASE)
        for section in sections
    ):
        return (page,), True
    return sections, False


def _normalize_meter_identifier(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.lstrip("#").strip()
    return normalized or None


def segment_document_id(document: InputDocument, segment: _ConsumptionSegment) -> str:
    page_token = "-".join(str(page.number) for page in segment.pages)
    meter_token = segment.meter_identifier or f"page-{page_token}"
    period_token = (segment.consumption_period or f"page-{page_token}").replace(" ", "")
    return f"{document.path.stem}:{segment.identifier}:{meter_token}:{period_token}"
