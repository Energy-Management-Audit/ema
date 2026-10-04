"""Validate extracted Fill facts against dossier and dataset evidence."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from functools import cached_property
from typing import Any

from ema.audit.applicability import fact_fields
from ema.audit.catalogue import CATALOGUE, AuditFact, fact_spec
from ema.audit.catalogue_labels import FACT_TYPES
from ema.audit.catalogue_types import fact_key, process_unit_name
from ema.audit.fill_files import file_ids, resolve_name, search, windows
from ema.audit.sections import recompute_ready, set_status
from ema.core.errors import EmaError
from ema.core.llm.agent import Tool
from ema.core.llm.types import ToolSpec
from ema.core.review.fields import fields, mark_absent, propose
from ema.core.review.models import Evidence, Field, PdfText, TextLoc
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

# Every argument is described: the first live run filled `name` and `source_key` by guessing.
_NAME = {
    "type": "string",
    "description": "exact dossier file name or its id from the task (e.g. F3)",
}
_FACT_KEY = {"type": "string", "description": "a fact key listed in the task"}
_REASON = {"type": "string", "description": "one sentence explaining the decision"}
_ARGUMENTS: dict[str, dict[str, dict[str, Any]]] = {
    "read_file": {
        "name": _NAME,
        "page": {"type": "integer", "description": "page number from 1; defaults to 1"},
    },
    "search_files": {
        "query": {"type": "string", "description": "words to find in the dossier files"}
    },
    "read_dataset": {
        "key": {
            "type": "string",
            "description": "one dataset field key; omit it to read all of this section's fields",
        }
    },
    "record_fact": {
        "key": _FACT_KEY,
        "value": {
            "type": ["string", "number"],
            "description": "the fact's value as stated in the quote",
        },
        "source_key": {
            "type": "string",
            "description": "only for a dataset field key from read_dataset; never a file name",
        },
        "name": _NAME,
        "quote": {
            "type": "string",
            "description": "verbatim excerpt of that file, 10-400 characters",
        },
    },
    "mark_missing": {"key": _FACT_KEY},
    "mark_later": {"reason": _REASON},
    "propose_na": {"reason": _REASON},
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

    @cached_property
    def pages(self) -> tuple[str, ...]:
        """What read_file serves: the PDF pages, else the text, each cut to bounded windows."""
        sources = self.page_texts or tuple(text for text in (self.text, self.ocr_text) if text)
        return tuple(part for source in sources for part in windows(source)) or ("",)


def _number(text: str) -> Decimal | None:
    """A number as a source writes it: `1.234,5`, `1 234,5` or `1234.5`."""
    raw = text.strip().replace(" ", "").replace("\u00a0", "")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        number = Decimal(raw)
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _typed(key: str, value: str | int | float) -> str | int | Decimal:
    """The value in its fact's type: a typed fact's number or year, else the text as given."""
    kind = FACT_TYPES[key][0] if key in FACT_TYPES else None
    if kind is None:
        return value if isinstance(value, str) else Decimal(str(value))
    number = _number(value) if isinstance(value, str) else Decimal(str(value))
    if kind == "year" and number is not None and number == int(number) and 1900 < number < 2100:
        return int(number)
    if kind == "number" and number is not None:
        return number
    raise EmaError("fact_type", "Tipul faptului nu este valid.", key)


def _number_in_quote(value: object, quote: str) -> bool:
    try:
        wanted = Decimal(str(value))
    except InvalidOperation:
        return False
    return any(_number(match.group()) == wanted for match in _NUMBER.finditer(quote))


class FillTools:
    def __init__(
        self, ws: Workspace, job: str, section: str, documents: dict[str, FillDocument]
    ) -> None:
        if section not in {item.id for item in CATALOGUE}:
            raise EmaError("section_missing", "Secţiunea lipseşte.", section)
        self.ws, self.job, self.section, self.documents = ws, job, section, documents

    def _document(self, name: str) -> tuple[str, FillDocument]:
        found = resolve_name(name, list(self.documents))
        if found is None:
            raise EmaError("file_missing", "Fişierul cerut lipseşte.", name)
        file_id = next(key for key, value in file_ids(self.documents).items() if value == found)
        return file_id, self.documents[found]

    def read_file(self, args: dict[str, Any]) -> object:
        file_id, document = self._document(str(args["name"]))
        page = int(args.get("page", 1))
        if not 1 <= page <= len(document.pages):
            raise EmaError("page_missing", "Pagina cerută lipseşte.", f"{file_id}: {page}")
        return {
            "file": file_id,
            "name": document.name,
            "page": page,
            "page_count": len(document.pages),
            "text": document.pages[page - 1],
        }

    def search_files(self, args: dict[str, Any]) -> object:
        query = str(args["query"]).strip()
        if not query:
            raise EmaError("query_missing", "Căutarea nu are text.", self.section)
        pages = {
            file_id: self.documents[name].pages
            for file_id, name in file_ids(self.documents).items()
        }
        return {"passages": search(pages, query)}

    def read_dataset(self, args: dict[str, Any]) -> object:
        # Only the section's own fields: the whole dataset is ~150k tokens on a real dossier.
        key = str(args.get("key", ""))
        dataset = {item.key: item for item in fields(self.ws, self.job)}
        section = next(item for item in CATALOGUE if item.id == self.section)
        scope = {item.key for ref in section.facts for item in fact_fields(ref, dataset)}
        scope |= {
            _STRUCTURED_SOURCE[str(ref)] for ref in section.facts if str(ref) in _STRUCTURED_SOURCE
        }
        available = [
            item for item in dataset.values() if item.key in scope and key in {"", item.key}
        ]
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
            raise EmaError("evidence_missing", "Valoarea din setul de date lipseşte.", source_key)
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
                "evidence_missing", "Dovada valorii din setul de date lipseşte.", source_key
            )
        return [Evidence.model_validate_json(row["data"]) for row in rows]

    def _validate_section_fact(self, key: str) -> None:
        section = next(item for item in CATALOGUE if item.id == self.section)
        if not any(isinstance(ref, AuditFact) and ref.value == key for ref in section.facts):
            raise EmaError("fact_section", "Faptul nu aparţine secţiunii active.", key)

    def _document_evidence(
        self, name: str, quote: str, value: object, page: int | None = None
    ) -> Evidence:
        _, document = self._document(name)
        pages = document.pages
        if page is not None and not 1 <= page <= len(pages):
            raise EmaError("page_missing", "Pagina cerută lipseşte.", str(page))
        quoted = (
            quote in pages[page - 1] if page is not None else any(quote in text for text in pages)
        )
        if not quote or not quoted:
            raise EmaError("evidence_quote", "Fragmentul citat nu apare în fişier.", name)
        if isinstance(value, int | float | Decimal) and not _number_in_quote(value, quote):
            raise EmaError("value_unverified", "Numărul nu apare în fragment.", name)
        if isinstance(value, str) and value not in quote:
            raise EmaError("value_unverified", "Textul nu apare în fragment.", name)
        located = page or next(
            (number for number, text in enumerate(document.page_texts, 1) if quote in text), None
        )
        locator = (
            PdfText(page=located, span=quote)
            if document.page_texts and located
            else TextLoc(span=quote)
        )
        evidence_id = hashlib.sha256(
            f"{self.job}:{document.sha}:{located}:{quote}".encode()
        ).hexdigest()
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
        if fact_key(key) not in _FACTS:
            raise EmaError("fact_unknown", "Faptul nu există în catalog.", key)
        self._validate_section_fact(fact_key(key))
        value = args["value"]
        if isinstance(value, bool) or not isinstance(value, str | int | float):
            raise EmaError("fact_type", "Tipul faptului nu este valid.", key)
        stored_value = _typed(key, value)
        source_key = str(args.get("source_key", ""))
        if source_key:
            if _STRUCTURED_SOURCE.get(key) != source_key:
                raise EmaError("fact_source", "Sursa nu corespunde faptului.", key)
            evidence = self._dataset_evidence(source_key, value)
        else:
            name, quote = str(args["name"]), str(args["quote"])
            page = int(args["page"]) if "page" in args else None
            evidence = [self._document_evidence(name, quote, stored_value, page)]
        kind, unit = FACT_TYPES.get(key, ("text" if isinstance(value, str) else "number", None))
        spec = fact_spec(key, kind, chapter=self.section, unit=unit)
        # An identifier given as a number (a CUI, a CAEN code) is stored as its text.
        stored_value = str(value) if spec.value_type == "text" else stored_value
        field = propose(self.ws, self.job, spec, stored_value, evidence, state="extracted")
        recompute_ready(self.ws, self.job)
        return {"key": field.key, "evidence": field.evidence}

    def passage_position(self, args: dict[str, Any]) -> tuple[int, int, int]:
        """Verify a passage quote without recording it; return its file, page and offset."""
        key = str(args["key"])
        if fact_key(key) not in _FACTS:
            raise EmaError("fact_unknown", "Faptul nu există în catalog.", key)
        self._validate_section_fact(fact_key(key))
        name, quote, page = str(args["name"]), str(args["quote"]), int(args["page"])
        self._document_evidence(name, quote, quote, page)
        file_id, document = self._document(name)
        return int(file_id.removeprefix("F")), page, document.pages[page - 1].index(quote)

    def mark_missing(self, args: dict[str, Any]) -> object:
        key = str(args["key"])
        if fact_key(key) not in _FACTS:
            raise EmaError("fact_unknown", "Faptul nu există în catalog.", key)
        self._validate_section_fact(fact_key(key))
        field = mark_absent(
            self.ws, self.job, fact_spec(key, "text", chapter=self.section), "not_found"
        )
        recompute_ready(self.ws, self.job)
        return {"missing": field.key}

    def record_unit_name(self, number: int, name: str | None, line: str = "") -> Field:
        """A process unit's heading: the verbatim line of its source file that names it.

        With no such line the field is missing, so the heading keeps its marker.
        """
        spec = fact_spec(process_unit_name(number), "text", chapter=self.section)
        if name is None:
            field = mark_absent(self.ws, self.job, spec, "not_found")
        else:
            evidence = [self._document_evidence(name, line, line)]
            field = propose(self.ws, self.job, spec, line, evidence, state="extracted")
        recompute_ready(self.ws, self.job)
        return field

    def mark_later(self, args: dict[str, Any]) -> object:
        reason = str(args["reason"]).strip()
        if not reason:
            raise EmaError("reason_missing", "Motivul lipseşte.", self.section)
        state = set_status(self.ws, self.job, self.section, Status.LATER, "agent", reason)
        return {"section": self.section, "status": state.status.value}

    def propose_na(self, args: dict[str, Any]) -> object:
        reason = str(args["reason"]).strip()
        if not reason:
            raise EmaError("reason_missing", "Motivul lipseşte.", self.section)
        state = set_status(self.ws, self.job, self.section, Status.NA_PROPOSED, "agent", reason)
        return {"section": self.section, "status": state.status.value, "reason": reason}

    def tools(self) -> dict[str, Tool]:
        def spec(name: str, description: str, required: tuple[str, ...] = ()) -> ToolSpec:
            parameters: dict[str, Any] = {"type": "object", "properties": _ARGUMENTS[name]}
            return ToolSpec(
                name, description, parameters | ({"required": list(required)} if required else {})
            )

        return {
            "read_file": Tool(
                spec(
                    "read_file", "Read one page of a dossier file, with its page_count", ("name",)
                ),
                self.read_file,
            ),
            "search_files": Tool(
                spec(
                    "search_files",
                    "Find passages of the dossier files that contain the query",
                    ("query",),
                ),
                self.search_files,
            ),
            "read_dataset": Tool(
                spec("read_dataset", "Read this section's located dataset fields"),
                self.read_dataset,
            ),
            "record_fact": Tool(
                spec("record_fact", "Record a fact with verified evidence", ("key", "value")),
                self.record_fact,
            ),
            "mark_missing": Tool(
                spec("mark_missing", "Record a missing fact", ("key",)), self.mark_missing
            ),
            "mark_later": Tool(
                spec("mark_later", "Defer a section with a reason", ("reason",)), self.mark_later
            ),
            "propose_na": Tool(
                spec("propose_na", "Propose n/a for an absent trigger", ("reason",)),
                self.propose_na,
            ),
        }
