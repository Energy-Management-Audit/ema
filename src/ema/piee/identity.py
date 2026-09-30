"""Source-backed client identity text for the PIEE's mapped spans."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from urllib.parse import urlsplit

from ema.core.office.numbers_ro import format_number
from ema.energy_data.anexa_cells import AnexaData
from ema.energy_data.source import Located


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


def ownership(anexa: AnexaData) -> str | None:
    state = percent_text(_value(anexa.identity, "ownership_state"))
    private = percent_text(_value(anexa.identity, "ownership_private"))
    if state is None or private is None:
        return None
    if Decimal(state[:-1].replace(",", ".")) == 0:
        return f"Companie cu capital integral privat: {private} capital privat."
    if Decimal(private[:-1].replace(",", ".")) == 0:
        return f"Companie cu capital integral de stat: {state} capital de stat."
    return f"Companie cu capital mixt: {state} capital de stat și {private} capital privat."


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
    auditor = _value(anexa.audit, "auditor")
    audit_date = _value(anexa.audit, "last_audit")
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
        "ownership": ownership(anexa),
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
        "audit_reference": (
            f"realizat de {auditor} la data de {audit_date}" if auditor and audit_date else None
        ),
        "production_name": production_name,
    }
