"""Source-backed client identity text for the PIEE's mapped spans."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from urllib.parse import urlsplit

from ema.core.office.numbers_ro import format_number
from ema.energy_data.anexa_cells import AnexaData
from ema.energy_data.source import Located


@dataclass(frozen=True)
class SpanText:
    text: str
    missing: tuple[tuple[int, int], ...] = ()


def _value(items: dict[str, Located], key: str) -> str | None:
    found = items.get(key)
    return str(found.value).strip() if found is not None and str(found.value).strip() else None


def website_target(anexa: AnexaData) -> str | None:
    raw = _value(anexa.identity, "website_target") or _value(anexa.identity, "website")
    if not raw:
        return None
    candidate = raw if "://" in raw else "https://" + raw
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
        return None
    if not re.fullmatch(r"[A-Za-z0-9.-]+", parsed.hostname) or "." not in parsed.hostname:
        return None
    return candidate


def percent_text(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = re.sub(r"\s+%", "%", raw.strip())
    if not re.fullmatch(r"\d+(?:[.,]\d+)?%", value):
        return None
    value = value.replace(".", ",")
    return value if 0 <= Decimal(value[:-1].replace(",", ".")) <= 100 else None


def ownership(anexa: AnexaData) -> SpanText | None:
    state = percent_text(_value(anexa.identity, "ownership_state"))
    private = percent_text(_value(anexa.identity, "ownership_private"))
    if state is None and private is None:
        return None
    state_number = Decimal(state[:-1].replace(",", ".")) if state is not None else None
    private_number = Decimal(private[:-1].replace(",", ".")) if private is not None else None
    if private is not None and (state_number == 0 or (state is None and private_number == 100)):
        return SpanText(f"Companie cu capital integral privat: {private} capital privat.")
    if state is not None and (private_number == 0 or (private is None and state_number == 100)):
        return SpanText(f"Companie cu capital integral de stat: {state} capital de stat.")
    if state_number == 0:
        text = "Companie cu capital integral privat: n.d. capital privat."
        start = text.index("n.d.")
        return SpanText(text, ((start, start + 4),))
    if private_number == 0:
        text = "Companie cu capital integral de stat: n.d. capital de stat."
        start = text.index("n.d.")
        return SpanText(text, ((start, start + 4),))
    text = (
        f"Companie cu capital mixt: {state or 'n.d.'} capital de stat "
        f"și {private or 'n.d.'} capital privat."
    )
    start = text.index("n.d.") if state is None or private is None else -1
    return SpanText(text, ((start, start + 4),) if start >= 0 else ())


def audit_year(anexa: AnexaData) -> str | None:
    found = anexa.audit.get("last_audit")
    if found is None:
        return None
    raw = found.value
    if isinstance(raw, date | datetime):
        return str(raw.year)
    if isinstance(raw, int) and not isinstance(raw, bool):
        return str(raw) if 1990 <= raw <= 2100 else None
    if isinstance(raw, str):
        years = set(re.findall(r"\b(?:19|20)\d{2}\b", raw))
        return next(iter(years)) if len(years) == 1 else None
    return None


def _phone(raw: str | None) -> str | None:
    if raw is None:
        return None
    digits = re.sub(r"\D", "", raw)
    return f"{digits[:4]} {digits[4:7]} {digits[7:]}" if len(digits) == 10 else raw


def production_share(raw: str | None) -> str | None:
    if raw is None:
        return None
    try:
        value = Decimal(raw)
    except ArithmeticError:
        return None
    return (
        format_number(value, 2, grouping=False) if value.is_finite() and 0 <= value <= 100 else None
    )


def footer_address(anexa: AnexaData) -> str | None:
    """Use only address components explicitly present in the supplied annex."""
    source = _value(anexa.identity, "address")
    if source is None:
        return None
    parts = [part.strip() for part in source.split(",")]
    if len(parts) < 4:
        return None
    number = re.search(r"\b(?:nr\.?|no\.?)\s*(\d+[A-Za-z]?)\b", parts[0], re.I)
    postcode = next(
        (re.search(r"\b\d{6}\b", part) for part in parts if re.search(r"\b\d{6}\b", part)), None
    )
    county = re.sub(r"^(?:jud\.?|județul|judetul)\s*", "", parts[-1], flags=re.I).strip()
    if number is None or postcode is None or not county:
        return None
    street = (parts[0][: number.start()] + parts[0][number.end() :]).strip(" ,.-")
    postal_index = next(index for index, part in enumerate(parts) if postcode.group(0) in part)
    city = parts[postal_index + 1].strip() if postal_index + 1 < len(parts) - 1 else ""
    if not street or not city:
        return None
    return f"{number.group(1)} {street}, {postcode.group(0)} {city}, {county} County"


def identity_values(
    anexa: AnexaData,
    generated_on: date,
    *,
    production_name: str | None = None,
    analysis_year: int | None = None,
) -> dict[str, str | None]:
    identity = anexa.identity
    phone, fax = _phone(_value(identity, "phone")), _phone(_value(identity, "fax"))
    caen_code = _value(identity, "caen_code")
    caen_description = _value(identity, "caen_description")
    site_1 = _value(identity, "site_1_name")
    site_2 = _value(identity, "site_2_name")
    site_1_address = _value(identity, "site_1_address")
    return {
        "client_name": _value(identity, "name"),
        "address": _value(identity, "address"),
        "site_1_name": site_1,
        "site_1_address": site_1_address,
        "site_2_name": site_2,
        "site_2_address": _value(identity, "site_2_address"),
        "site_1_production_share": production_share(_value(identity, "site_1_production_share")),
        "site_2_production_share": production_share(_value(identity, "site_2_production_share")),
        "analysis_year": str(analysis_year) if analysis_year is not None else None,
        "footer_address": footer_address(anexa),
        "cui": re.sub(r"^RO\s*", "", _value(identity, "cui") or "", flags=re.I) or None,
        "registrul_comertului": _value(identity, "registrul_comertului"),
        "ownership": line.text if (line := ownership(anexa)) else None,
        "phone": phone,
        "fax": fax,
        "phone_fax": (
            "; ".join(part for part in (phone, f"Fax: {fax}" if fax else None) if part) + ";"
            if phone or fax
            else None
        ),
        "website": website_target(anexa),
        "website_target": website_target(anexa),
        "caen": f"{caen_code}: {caen_description}" if caen_code and caen_description else None,
        "contact_person": _value(identity, "consumer_contact_person"),
        "generation_date": generated_on.strftime("%d.%m.%Y"),
        "production_name": production_name,
    }
