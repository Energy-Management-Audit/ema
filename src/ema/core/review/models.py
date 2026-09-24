"""Typed review records shared by workflows and interfaces."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal, cast

from pydantic import BaseModel, ConfigDict, model_validator
from pydantic import Field as PydanticField


class PdfRegion(BaseModel):
    kind: Literal["pdf_region"] = "pdf_region"
    page: int
    bbox: tuple[float, float, float, float]


class PdfText(BaseModel):
    kind: Literal["pdf_text"] = "pdf_text"
    page: int
    span: str


class TextLoc(BaseModel):
    kind: Literal["text"] = "text"
    span: str


class Cell(BaseModel):
    kind: Literal["cell"] = "cell"
    sheet: str
    ref: str


class DocxLoc(BaseModel):
    kind: Literal["docx"] = "docx"
    paragraph: int | None = None
    table: int | None = None
    row: int | None = None
    col: int | None = None

    @model_validator(mode="after")
    def location_required(self) -> DocxLoc:
        if self.paragraph is None and self.table is None:
            raise ValueError("docx locator needs a paragraph or table")
        return self


class Photo(BaseModel):
    kind: Literal["photo"] = "photo"
    region: tuple[float, float, float, float] | None = None


class Url(BaseModel):
    kind: Literal["url"] = "url"
    url: str
    snapshot_sha: str


class Manual(BaseModel):
    kind: Literal["manual"] = "manual"
    who: str
    note: str | None = None


Locator = Annotated[
    PdfRegion | PdfText | TextLoc | Cell | DocxLoc | Photo | Url | Manual,
    PydanticField(discriminator="kind"),
]
Actor = Literal["ema", "user", "agent"]
ValueType = Literal["number", "text", "year", "date", "enum"]


class Derivation(BaseModel):
    formula_id: str
    inputs: list[str]
    factor_version: str


class Evidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    provenance: Literal["document", "online", "calculated", "manual"]
    file_sha: str | None = None
    locator: Locator | None = None
    method: Literal["questionnaire", "anexa", "prelucrare", "invoice", "online", "manual", "calc"]
    retrieved_at: datetime
    quote: str | None = None
    trust_reason: str | None = None
    highlight: Literal["exact", "page", "none"]
    derivation: Derivation | None = None
    decision_id: str | None = None

    @model_validator(mode="after")
    def valid_provenance(self) -> Evidence:
        expected = {
            "online": "online",
            "calc": "calculated",
            "manual": "manual",
        }.get(self.method, "document")
        if self.provenance != expected:
            raise ValueError("provenance and method disagree")
        if self.provenance == "document" and (
            not self.file_sha or self.locator is None or isinstance(self.locator, Url | Manual)
        ):
            raise ValueError("document evidence needs a file version and document locator")
        if self.provenance == "online" and (
            not isinstance(self.locator, Url) or not (self.quote or self.trust_reason)
        ):
            raise ValueError("online evidence needs a URL, snapshot, and quote or trust reason")
        if self.provenance == "calculated" and self.derivation is None:
            raise ValueError("calculated evidence needs formula, inputs and factor version")
        if self.provenance == "manual" and not isinstance(self.locator, Manual):
            raise ValueError("manual evidence needs an actor")
        return self


class Candidate(BaseModel):
    id: str
    value: Any
    evidence: list[str]


class Field(BaseModel):
    id: str
    job_id: str
    chapter: str = ""
    key: str
    label: str
    value_type: ValueType
    unit: str | None = None
    required: bool = False
    value: Any = None
    revision: int = 1
    state: Literal["supplied", "extracted", "enriched", "calculated", "manual"]
    presence: Literal["found", "not_found", "failed"]
    review: Literal["pending", "accepted", "corrected", "rejected"] = "pending"
    confidence: Literal["exact", "partial", "conflict", "none"] = "none"
    evidence: list[str] = PydanticField(default_factory=list)
    derivation: Derivation | None = None
    alternatives: list[Candidate] = PydanticField(default_factory=list[Candidate])
    chosen: str | None = None
    failure: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_number(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        values = dict(cast("dict[str, Any]", data))
        if values.get("value_type") != "number":
            return values
        try:
            if values.get("value") is not None:
                values["value"] = Decimal(str(values["value"]))
            candidates = cast("list[Candidate | dict[str, Any]]", values.get("alternatives", []))
            normalized: list[dict[str, Any]] = []
            for candidate in candidates:
                item = candidate.model_dump() if isinstance(candidate, Candidate) else candidate
                normalized.append({**item, "value": Decimal(str(item["value"]))})
            values["alternatives"] = normalized
        except (InvalidOperation, KeyError, TypeError) as exc:
            raise ValueError("invalid number") from exc
        return values

    @model_validator(mode="after")
    def valid_state(self) -> Field:
        if (self.value is None) != (self.presence != "found"):
            raise ValueError("value and presence disagree")
        if self.state == "manual" and (self.value is None or not self.evidence):
            raise ValueError("manual value needs evidence")
        if self.presence == "failed" and not self.failure:
            raise ValueError("failed presence needs a cause")
        if self.presence != "failed" and self.failure:
            raise ValueError("failure requires failed presence")
        values = [candidate.value for candidate in self.alternatives]
        conflict = (
            len(values) >= 2
            and any(value != values[0] for value in values[1:])
            and self.chosen is None
        )
        if (self.confidence == "conflict") != conflict:
            raise ValueError("confidence and alternatives disagree")
        if self.chosen is not None and self.chosen not in {item.id for item in self.alternatives}:
            raise ValueError("chosen candidate does not exist")
        for value in [self.value, *values]:
            if value is None:
                continue
            number = isinstance(value, Decimal) and value.is_finite()
            year = isinstance(value, int) and not isinstance(value, bool)
            text = isinstance(value, str)
            valid = {"number": number, "year": year, "text": text, "enum": text, "date": text}
            if not valid[self.value_type]:
                raise ValueError("value does not match value_type")
        return self


class Decision(BaseModel):
    id: str
    at: datetime
    actor: Actor
    field_id: str
    target_kind: Literal["field", "section"] = "field"
    on_revision: int
    action: Literal["accept", "correct", "reject", "choose", "status", "undo"]
    detail: str | None = None
    before: Field | dict[str, Any]
    after: Field | dict[str, Any]
    batch_id: str | None = None
    undone_by: str | None = None


class Issue(BaseModel):
    code: str
    field_id: str | None = None
    message: str


class Readiness(BaseModel):
    draft_ok: bool
    final_ok: bool
    blocking: list[Issue] = PydanticField(default_factory=list[Issue])
    warnings: list[Issue] = PydanticField(default_factory=list[Issue])
    next: list[str] = PydanticField(default_factory=list[str])


class FieldSpec(BaseModel):
    key: str
    label: str
    value_type: ValueType
    required: bool = False
    unit: str | None = None
    chapter: str = ""


class Approval(BaseModel):
    id: str
    job_id: str
    output_id: str
    readiness_hash: str
    on_decision: str | None
    at: datetime
    actor: Actor
