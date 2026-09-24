"""Auditable tools exposed to the per-section audit Fill agent."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from ema.audit.catalogue import CATALOGUE, AuditFact
from ema.audit.sections import recompute_ready, set_status
from ema.core.errors import EmaError
from ema.core.llm.agent import Tool
from ema.core.llm.types import ToolSpec
from ema.core.review.fields import fields, mark_absent, propose
from ema.core.review.models import Evidence, FieldSpec, PdfText, TextLoc
from ema.core.review.section_transition import Status
from ema.core.workspace import Workspace

_NUMBER = re.compile(r"(?<!\w)[+-]?\d[\d .\u00a0]*(?:,\d+)?(?!\w)")
_FACTS = frozenset(item.value for item in AuditFact)
_STRUCTURED_SOURCE = {
    "audit.company_name": "audit.company_name",
    "audit.cui": "audit.cui",
    "audit.registrul_comertului": "audit.registrul_comertului",
    "audit.address": "audit.address",
    "audit.phone": "audit.phone",
    "audit.website": "audit.website",
    "audit.caen_code": "audit.caen_code",
    "audit.caen_description": "audit.caen_description",
    "audit.ownership_state": "audit.ownership_state",
    "audit.ownership_private": "audit.ownership_private",
}


@dataclass(frozen=True)
class FillDocument:
    name: str
    text: str
    ocr_text: str = ""
    page_images: tuple[str, ...] = ()
    page_texts: tuple[str, ...] = ()
    file_sha: str | None = None

    @property
    def sha(self) -> str:
        return (
            self.file_sha
            or hashlib.sha256(
                "\n".join((self.text, self.ocr_text, *self.page_texts)).encode("utf-8")
            ).hexdigest()
        )


def _number_in_quote(value: object, quote: str) -> bool:
    try:
        wanted = Decimal(str(value))
    except InvalidOperation:
        return False
    for match in _NUMBER.finditer(quote):
        raw = match.group().strip().replace(" ", "").replace("\u00a0", "")
        if not raw:
            continue
        if "," in raw:
            raw = raw.replace(".", "").replace(",", ".")
        try:
            if Decimal(raw) == wanted:
                return True
        except InvalidOperation:
            continue
    return False


class FillTools:
    def __init__(
        self, ws: Workspace, job: str, section: str, documents: dict[str, FillDocument]
    ) -> None:
        if section not in {item.id for item in CATALOGUE}:
            raise EmaError("section_missing", "Secțiunea lipsește.", section)
        self.ws, self.job, self.section, self.documents = ws, job, section, documents

    def read_file(self, args: dict[str, Any]) -> object:
        name = str(args["name"])
        document = self.documents.get(name)
        if document is None:
            raise EmaError("file_missing", "Fișierul cerut lipsește.", name)
        return {
            "text": document.text,
            "ocr_text": document.ocr_text,
            "page_texts": document.page_texts,
            "page_images": document.page_images,
        }

    def read_dataset(self, args: dict[str, Any]) -> object:
        key = str(args.get("key", ""))
        available = [item for item in fields(self.ws, self.job) if not key or item.key == key]
        return [
            {
                "key": item.key,
                "value": str(item.value),
                "unit": item.unit,
                "evidence": item.evidence,
                "presence": item.presence,
            }
            for item in available
        ]

    def _dataset_evidence(self, source_key: str, value: object) -> list[Evidence]:
        field = next((item for item in fields(self.ws, self.job) if item.key == source_key), None)
        if field is None or field.presence != "found" or not field.evidence:
            raise EmaError("evidence_missing", "Valoarea din setul de date lipsește.", source_key)
        if isinstance(value, int | float):
            if Decimal(str(field.value)) != Decimal(str(value)):
                raise EmaError("value_unverified", "Valoarea nu corespunde sursei.", source_key)
        elif str(field.value) != str(value):
            raise EmaError("value_unverified", "Valoarea nu corespunde sursei.", source_key)
        placeholders = ",".join("?" for _ in field.evidence)
        with self.ws.connect() as db:
            rows = db.execute(
                f"SELECT id, data FROM evidence WHERE job_id=? AND id IN ({placeholders})",
                (self.job, *field.evidence),
            ).fetchall()
        if len(rows) != len(field.evidence) or {row["id"] for row in rows} != set(field.evidence):
            raise EmaError(
                "evidence_missing", "Dovada valorii din setul de date lipsește.", source_key
            )
        return [Evidence.model_validate_json(row["data"]) for row in rows]

    def _validate_section_fact(self, key: str) -> None:
        section = next(item for item in CATALOGUE if item.id == self.section)
        if not any(isinstance(ref, AuditFact) and ref.value == key for ref in section.facts):
            raise EmaError("fact_section", "Faptul nu aparține secțiunii active.", key)

    def _document_evidence(self, name: str, quote: str, value: object) -> Evidence:
        document = self.documents.get(name)
        if document is None:
            raise EmaError("file_missing", "Fișierul cerut lipsește.", name)
        if not quote or not any(
            quote in text for text in (document.text, document.ocr_text, *document.page_texts)
        ):
            raise EmaError("evidence_quote", "Fragmentul citat nu apare în fișier.", name)
        if isinstance(value, int | float) and not _number_in_quote(value, quote):
            raise EmaError("value_unverified", "Numărul nu apare în fragment.", name)
        if isinstance(value, str) and value not in quote:
            raise EmaError("value_unverified", "Textul nu apare în fragment.", name)
        page = next(
            (number for number, text in enumerate(document.page_texts, 1) if quote in text),
            None,
        )
        locator = PdfText(page=page, span=quote) if page is not None else TextLoc(span=quote)
        evidence_id = hashlib.sha256(f"{document.sha}:{quote}".encode()).hexdigest()
        with self.ws.connect() as db:
            previous = db.execute(
                "SELECT data FROM evidence WHERE id=? AND job_id=?", (evidence_id, self.job)
            ).fetchone()
        return Evidence(
            id=evidence_id,
            provenance="document",
            file_sha=document.sha,
            locator=locator,
            method="questionnaire",
            retrieved_at=(
                Evidence.model_validate_json(previous["data"]).retrieved_at
                if previous
                else datetime.now(UTC)
            ),
            quote=quote,
            highlight="exact",
        )

    def record_fact(self, args: dict[str, Any]) -> object:
        key = str(args["key"])
        if key not in _FACTS:
            raise EmaError("fact_unknown", "Faptul nu există în catalog.", key)
        self._validate_section_fact(key)
        value = args["value"]
        if isinstance(value, bool) or not isinstance(value, str | int | float):
            raise EmaError("fact_type", "Tipul faptului nu este valid.", key)
        source_key = str(args.get("source_key", ""))
        if source_key:
            if _STRUCTURED_SOURCE.get(key) != source_key:
                raise EmaError("fact_source", "Sursa nu corespunde faptului.", key)
            evidence = self._dataset_evidence(source_key, value)
        else:
            name, quote = str(args["name"]), str(args["quote"])
            evidence = [self._document_evidence(name, quote, value)]
        spec = FieldSpec(
            key=key,
            label=key,
            value_type="number" if isinstance(value, int | float) else "text",
            chapter=self.section,
        )
        stored_value = Decimal(str(value)) if isinstance(value, int | float) else value
        field = propose(self.ws, self.job, spec, stored_value, evidence, state="extracted")
        recompute_ready(self.ws, self.job)
        return {"key": field.key, "evidence": field.evidence}

    def mark_missing(self, args: dict[str, Any]) -> object:
        key = str(args["key"])
        if key not in _FACTS:
            raise EmaError("fact_unknown", "Faptul nu există în catalog.", key)
        self._validate_section_fact(key)
        field = mark_absent(self.ws, self.job, key, "not_found")
        recompute_ready(self.ws, self.job)
        return {"missing": field.key}

    def mark_later(self, args: dict[str, Any]) -> object:
        reason = str(args["reason"]).strip()
        if not reason:
            raise EmaError("reason_missing", "Motivul lipsește.", self.section)
        state = set_status(self.ws, self.job, self.section, Status.LATER, "agent", reason)
        return {"section": self.section, "status": state.status.value}

    def propose_na(self, args: dict[str, Any]) -> object:
        reason = str(args["reason"]).strip()
        if not reason:
            raise EmaError("reason_missing", "Motivul lipsește.", self.section)
        state = set_status(self.ws, self.job, self.section, Status.NA_PROPOSED, "agent", reason)
        return {"section": self.section, "status": state.status.value, "reason": reason}

    def tools(self) -> dict[str, Tool]:
        string = {"type": "string"}
        return {
            "read_file": Tool(
                ToolSpec(
                    "read_file",
                    "Read dossier text/OCR/page images",
                    {"type": "object", "properties": {"name": string}, "required": ["name"]},
                ),
                self.read_file,
            ),
            "read_dataset": Tool(
                ToolSpec(
                    "read_dataset",
                    "Read a located dataset field",
                    {"type": "object", "properties": {"key": string}},
                ),
                self.read_dataset,
            ),
            "record_fact": Tool(
                ToolSpec(
                    "record_fact",
                    "Record a fact with verified evidence",
                    {
                        "type": "object",
                        "properties": {
                            "key": string,
                            "value": {"type": ["string", "number"]},
                            "source_key": string,
                            "name": string,
                            "quote": string,
                        },
                        "required": ["key", "value"],
                    },
                ),
                self.record_fact,
            ),
            "mark_missing": Tool(
                ToolSpec(
                    "mark_missing",
                    "Record a missing fact",
                    {"type": "object", "properties": {"key": string}, "required": ["key"]},
                ),
                self.mark_missing,
            ),
            "mark_later": Tool(
                ToolSpec(
                    "mark_later",
                    "Defer a section with a reason",
                    {"type": "object", "properties": {"reason": string}, "required": ["reason"]},
                ),
                self.mark_later,
            ),
            "propose_na": Tool(
                ToolSpec(
                    "propose_na",
                    "Propose n/a for an absent trigger",
                    {"type": "object", "properties": {"reason": string}, "required": ["reason"]},
                ),
                self.propose_na,
            ),
        }
