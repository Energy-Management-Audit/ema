"""Read the buyer column from ALIVE scans using Tesseract word positions."""

from __future__ import annotations

import re
from collections import Counter

from ema.invoices.configuration.field_catalog import CLIENT_NAME, CLIENT_TAX_ID
from ema.invoices.models import FieldStatus, FieldValue, InputDocument, SourceEvidence
from ema.invoices.parsers.client_identity import extract_client_identity_fields

_LEGAL = re.compile(r"\b(?:S\.?R\.?L\.?|S\.?A\.?)\s*$", re.I)
_CUI = re.compile(r"\bCIF\s*:\s*(RO\s*\d{5,10})\b", re.I)


def _right_lines(document: InputDocument) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    for page in document.pages:
        if not page.blocks:
            continue
        middle = max(block.x1 for block in page.blocks) / 2
        lines: list[tuple[float, list[tuple[float, str]]]] = []
        for block in sorted(
            (part for part in page.blocks if part.x0 > middle), key=lambda part: (part.y0, part.x0)
        ):
            if lines and abs(block.y0 - lines[-1][0]) < 2.5:
                lines[-1][1].append((block.x0, block.text))
            else:
                lines.append((block.y0, [(block.x0, block.text)]))
        result.extend(
            (page.number, " ".join(text for _, text in sorted(words))) for _, words in lines
        )
    return result


def buyer_fields(document: InputDocument) -> dict[str, FieldValue]:
    fields = extract_client_identity_fields(document)
    names: list[tuple[str, SourceEvidence]] = []
    taxes: list[tuple[str, SourceEvidence]] = []
    in_buyer = False
    for page, line in _right_lines(document):
        if line.strip().casefold() == "client":
            in_buyer = True
            continue
        if not in_buyer:
            continue
        if match := _CUI.search(line):
            taxes.append(
                (match[1].replace(" ", "").upper(), SourceEvidence(page, line, "client tax id"))
            )
            in_buyer = False
        elif _LEGAL.search(line) and len(line) < 100:
            names.append((line.strip(), SourceEvidence(page, line, "client name")))
    for key, values in ((CLIENT_NAME, names), (CLIENT_TAX_ID, taxes)):
        if not values:
            continue
        counts = Counter(value for value, _ in values)
        selected = counts.most_common(1)[0][0]
        if len(counts) == 1:
            fields[key] = FieldValue(
                selected, FieldStatus.EXTRACTED, tuple(proof for _, proof in values)
            )
        else:
            fields[key] = FieldValue(
                selected,
                FieldStatus.AMBIGUOUS,
                tuple(proof for _, proof in values),
                "Valorile tipărite pentru client diferă între pagini.",
            )
    return fields
