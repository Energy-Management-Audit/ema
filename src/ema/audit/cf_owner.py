"""Locate a company's CIF in land-registry owner entries by label and name."""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pypdfium2 as pdfium

from ema.core.errors import EmaError
from ema.core.review.models import Evidence, PdfText

_CIF = re.compile(r"\bCIF\s*:\s*(\d{2,10})\b", re.IGNORECASE)
_OWNER = re.compile(r"\b(proprietar(?:i)?|titular(?:i)?)\b", re.IGNORECASE)


def _tokens(text: str) -> set[str]:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return {token.casefold() for token in re.findall(r"[A-Za-z]+", ascii_text) if len(token) >= 2}


def company_from_necesar_name(path: Path) -> str:
    name = re.sub(r"^\d+\.\s*Necesar info\s*", "", path.stem, flags=re.IGNORECASE)
    return re.sub(r"[_\s]+\d{4}$", "", name).strip(" _")


@dataclass(frozen=True)
class LocatedCui:
    cui: str
    evidence: Evidence
    source: Path


def read_owner_cui(extracts: list[Path], company: str) -> LocatedCui:
    wanted = _tokens(company)
    if not wanted:
        raise EmaError("company_missing", "Numele clientului lipseşte.", "")
    matches: dict[str, tuple[Evidence, Path]] = {}
    for source in extracts:
        document = pdfium.PdfDocument(source)
        sha = hashlib.sha256(source.read_bytes()).hexdigest()
        for page in range(min(len(document), 2)):
            lines = document[page].get_textpage().get_text_range().splitlines()
            for index, line in enumerate(lines):
                found = _CIF.search(line)
                if not found or not wanted <= _tokens(line):
                    continue
                context = "\n".join(lines[max(0, index - 12) : index + 1])
                if not _OWNER.search(context):
                    continue
                evidence = Evidence(
                    id=uuid.uuid4().hex,
                    provenance="document",
                    file_sha=sha,
                    locator=PdfText(page=page + 1, span=line),
                    method="anexa",
                    retrieved_at=datetime.now(UTC),
                    quote=line,
                    highlight="exact",
                )
                matches[found.group(1)] = (evidence, source)
    if len(matches) != 1:
        reason = "cui_missing" if not matches else "cui_conflict"
        raise EmaError(reason, "Codul fiscal al proprietarului necesită verificare.", reason)
    cui, (evidence, source) = next(iter(matches.items()))
    return LocatedCui(cui, evidence, source)
