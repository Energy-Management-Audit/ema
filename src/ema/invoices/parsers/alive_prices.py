"""ALIVE price lines, including the scan's occasional decimal split."""

from __future__ import annotations

import re
from decimal import Decimal

from ema.invoices.models import EnergyCategory, InputDocument, PriceDetail, SourceEvidence
from ema.invoices.parsers.engie_text import plain_text
from ema.invoices.parsers.normalization import normalize_quantity_and_price

ROW = re.compile(
    r"^\s*\d{1,2}[.)]?\s+(?P<description>.+?)\s+"
    r"(?P<unit>MWh|kWh|kVArh)\]?\s+(?P<quantity>[-−–]?[0-9][0-9.,]*)\s+"
    r"(?P<price>[-−–]?[0-9][0-9.,]*)\s+(?P<net>[-−–]?[0-9][0-9.,]*)\s+"
    r"(?P<vat>[-−–]?[0-9][0-9.,]*)\s*$",
    re.I,
)
EDI_ROW = re.compile(
    r"^\s*(?P<description>.+?)\s+(?P<quantity>[-−–]?[0-9][0-9.,]*)\s+"
    r"(?P<unit>MWh|kWh|kVArh|MVArh|MAH)\s+(?P<price>[-−–]?[0-9][0-9.,]*)\s+"
    r"[0-9]{1,2}(?:[.,][0-9]+)?\s+(?P<net>[-−–]?[0-9][0-9.,]*)\s*$",
    re.I,
)
REACTIVE_READING = re.compile(
    r"energie\s+reactiva\s+(?P<kind>inductiva|capacitiva).*?"
    r"(?P<quantity>[-−–]?[0-9][0-9.]*)[\]\s|]*(?:kvarh)\b",
    re.I,
)


def category(description: str) -> EnergyCategory:
    value = plain_text(description)
    if "pierderi" in value and "energie" in value:
        return EnergyCategory.ACTIVE_ENERGY_LOSSES
    if "energie reactiva capacitiva" in value:
        return EnergyCategory.REACTIVE_CAPACITIVE
    if "energie reactiva inductiva" in value:
        return EnergyCategory.REACTIVE_INDUCTIVE
    if "certificate verzi" in value:
        return EnergyCategory.GREEN_CERTIFICATES
    if "energie electrica activa livrata" in value or "avans energie electrica livrata" in value:
        return EnergyCategory.ACTIVE_ENERGY
    return EnergyCategory.OTHER


def _unit_price(quantity: Decimal, extracted: Decimal, net: Decimal) -> Decimal:
    if not quantity:
        return extracted
    calculated = net / quantity
    tolerance = max(abs(calculated) * Decimal("0.01"), Decimal("0.02"))
    return calculated if abs(extracted - calculated) > tolerance else extracted


def _number(raw: str) -> Decimal:
    """ALIVE's machine rows use dot decimals; other rows use comma decimals."""
    cleaned = raw.replace("−", "-").replace("–", "-")
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    elif cleaned.count(".") > 1:
        whole, fraction = cleaned.rsplit(".", 1)
        cleaned = f"{whole.replace('.', '')}.{fraction}"
    return Decimal(cleaned)


def _meter_quantity(line: str, match: re.Match[str]) -> Decimal:
    quantity = _number(match["quantity"])
    indexes = re.findall(r"\b\d+\.\d+\b", line[: match.start("quantity")])
    return Decimal(0) if len(indexes) >= 2 and indexes[-1] == indexes[-2] else quantity


def price_details(document: InputDocument) -> list[PriceDetail]:
    details: list[PriceDetail] = []
    seen: set[tuple[object, ...]] = set()
    for page in document.pages:
        for line in page.text.splitlines():
            cleaned = re.sub(r"(?<=\d)\s+(?=\d{2}\s*$)", ".", line.replace("|", " "))
            match = ROW.match(cleaned) or EDI_ROW.match(cleaned)
            if match is None:
                continue
            description = match["description"].strip()
            description = re.sub(
                r"\bContribuie(?=\s+cogenerare)", "Contributie", description, flags=re.I
            )
            kind = category(description)
            quantity = _number(match["quantity"])
            price = _unit_price(quantity, _number(match["price"]), _number(match["net"]))
            net = _number(match["net"])
            key = (kind, plain_text(description), quantity, price, net)
            if key in seen:
                continue
            seen.add(key)
            source_unit = match["unit"]
            normalized_source_unit = (
                "MVArh"
                if kind in {EnergyCategory.REACTIVE_CAPACITIVE, EnergyCategory.REACTIVE_INDUCTIVE}
                and source_unit.casefold() in {"mah", "mvarh"}
                else source_unit
            )
            normalized_quantity, unit, normalized_price = normalize_quantity_and_price(
                quantity, price, normalized_source_unit
            )
            details.append(
                PriceDetail(
                    kind,
                    description,
                    quantity,
                    source_unit,
                    price,
                    normalized_quantity,
                    unit,
                    normalized_price,
                    net,
                    SourceEvidence(page.number, line.strip(), "invoice price row"),
                )
            )
    present = {detail.category for detail in details}
    for page in document.pages:
        for line in page.text.splitlines():
            normalized = plain_text(line)
            if "energie reactiva" in normalized:
                # Tesseract often reads the printed zero in the meter table as Q or oo.
                normalized = re.sub(r"\b(?:q|oo)\s+(?=kvarh\b)", "0 ", normalized)
            match = REACTIVE_READING.search(normalized)
            if match is None:
                continue
            kind = (
                EnergyCategory.REACTIVE_INDUCTIVE
                if match["kind"] == "inductiva"
                else EnergyCategory.REACTIVE_CAPACITIVE
            )
            if kind in present:
                continue
            quantity = _meter_quantity(normalized, match)
            details.append(
                PriceDetail(
                    kind,
                    f"Energie reactiva {match['kind']} (masurata, nefacturata)",
                    quantity,
                    "kVArh",
                    Decimal(0),
                    quantity,
                    "kVArh",
                    Decimal(0),
                    Decimal(0),
                    SourceEvidence(page.number, line.strip(), "meter reading"),
                )
            )
            present.add(kind)
    return details
