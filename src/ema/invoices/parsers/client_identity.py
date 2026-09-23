from __future__ import annotations

import re

from ema.invoices.configuration.field_catalog import CLIENT_NAME, CLIENT_TAX_ID
from ema.invoices.models import (
    FieldStatus,
    FieldValue,
    InputDocument,
    SourceEvidence,
    normalize_client_name,
)

_NAME_PATTERN = re.compile(
    r"(?im)^\s*(?P<label>denumire\s+client|nume\s+client|client|"
    r"cump[aă]r[aă]tor|beneficiar|consumator)"
    r"\s*[:\-]\s*(?P<value>[^\r\n]+)"
)
_TAX_PATTERN = re.compile(
    r"(?i)\b(?:CUI|CIF|C\.?\s*L\.?\s*F\.?|C\.?\s*F\.?|cod\s+fiscal|"
    r"cod\s+unic\s+de\s+[iî]nregistrare)"
    r"(?:\s+(?:client|cump[aă]r[aă]tor|beneficiar))?\s*[:\-]?\s*(?P<value>R[O0]\s*\d{2,10}|\d{2,10})\b"
)
_INLINE_TAX = re.compile(
    r"(?i)\b(?:CUI|CIF|cod\s+fiscal)\s*[:\-]?\s*(?P<value>R[O0]\s*\d{2,10}|\d{2,10})\b"
)
_TRAILING_LABELS = re.compile(r"(?i)\s+(?:CUI|CIF|cod\s+fiscal|adresa|sediu)\s*[:\-].*$")
_LEGAL_NAME = re.compile(r"(?i)^(.+?\bS\.?\s*(?:A\.?|R\.?\s*L\.?))(?=\s|$)")


def extract_client_identity_fields(document: InputDocument) -> dict[str, FieldValue]:
    name_candidates: list[tuple[str, SourceEvidence]] = []
    tax_candidates: list[tuple[str, SourceEvidence]] = []
    first_client_page: int | None = None
    for page in document.pages:
        text = page.text
        for match in _NAME_PATTERN.finditer(text):
            if first_client_page is None:
                first_client_page = page.number
            raw = match.group("value").strip()
            tax_match = _INLINE_TAX.search(raw)
            if (
                page.number == first_client_page
                and tax_match
                and match.group("label").casefold() != "nume client"
            ):
                tax_candidates.append(
                    (
                        _display_tax_id(tax_match.group("value")),
                        SourceEvidence(page.number, match.group(0).strip(), "client tax id"),
                    )
                )
            name = _clean_name(raw)
            if name:
                name_candidates.append(
                    (name, SourceEvidence(page.number, match.group(0).strip(), "client name"))
                )

        lines = text.splitlines()
        client_line_indexes = [
            index
            for index, line in enumerate(lines)
            if re.search(
                r"(?i)^\s*(?:nume\s+client|client|cump[aă]r[aă]tor|beneficiar|consumator)"
                r"\s*[:\-]",
                line,
            )
        ]
        if page.number != first_client_page:
            client_line_indexes = []
        for index in client_line_indexes:
            context = "\n".join(lines[index + 1 : index + 10])
            match = _TAX_PATTERN.search(context)
            if match is not None:
                tax_candidates.append(
                    (
                        _display_tax_id(match.group("value")),
                        SourceEvidence(page.number, match.group(0).strip(), "client tax id"),
                    )
                )

    names = _deduplicate(name_candidates)
    taxes = _deduplicate(tax_candidates)
    return {
        CLIENT_NAME: _candidate_field(names, "Denumirea clientului nu a putut fi identificată."),
        CLIENT_TAX_ID: _optional_candidate_field(taxes),
    }


def _clean_name(raw: str) -> str | None:
    name = _TRAILING_LABELS.sub("", raw).strip(" ,;:-")
    if legal_name := _LEGAL_NAME.match(name):
        return legal_name.group(1).strip()
    return None if re.search(r"[$\d,]", name) else name


def _candidate_field(
    candidates: list[tuple[str, SourceEvidence]], missing_message: str
) -> FieldValue:
    if not candidates:
        return FieldValue(None, FieldStatus.MISSING, message=missing_message)
    if len(candidates) > 1:
        values = ", ".join(value for value, _evidence in candidates)
        return FieldValue(
            candidates[0][0],
            FieldStatus.AMBIGUOUS,
            tuple(evidence for _value, evidence in candidates),
            f"Au fost găsite mai multe valori posibile: {values}",
        )
    value, evidence = candidates[0]
    return FieldValue(value, FieldStatus.EXTRACTED, (evidence,))


def _optional_candidate_field(candidates: list[tuple[str, SourceEvidence]]) -> FieldValue:
    if not candidates:
        return FieldValue(None, FieldStatus.NOT_PROVIDED)
    return _candidate_field(candidates, "")


def _deduplicate(
    candidates: list[tuple[str, SourceEvidence]],
) -> list[tuple[str, SourceEvidence]]:
    unique: dict[str, tuple[str, SourceEvidence]] = {}
    for value, evidence in candidates:
        key = normalize_client_name(value) or value.casefold()
        unique.setdefault(key, (value, evidence))
    return list(unique.values())


def _display_tax_id(value: str) -> str:
    compact = re.sub(r"\s+", "", value).upper()
    if compact.startswith("R0"):
        compact = f"RO{compact[2:]}"
    return compact
