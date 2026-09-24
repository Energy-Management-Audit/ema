"""Structured, fact-addressed drafts for catalogue sections in chapters two and three."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ema.audit.catalogue import CATALOGUE

SECTION_FACTS = {
    section.id: frozenset(str(fact) for fact in section.facts)
    for section in CATALOGUE
    if section.chapter in (2, 3) and section.parent is not None
}


class DraftText(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    fact_ids: list[str] = Field(default_factory=list[str])
    kind: Literal["body", "bullet", "caption"] = "body"


class DraftTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    caption: DraftText
    rows: list[list[DraftText]]

    @model_validator(mode="after")
    def rectangular(self) -> DraftTable:
        if (
            not self.rows
            or not self.rows[0]
            or any(len(row) != len(self.rows[0]) for row in self.rows)
        ):
            raise ValueError("draft table needs nonempty rectangular rows")
        return self


class DraftFigure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_id: str
    caption: DraftText


class SectionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section: str
    status: Literal["drafted", "missing"]
    paragraphs: list[DraftText] = Field(default_factory=list[DraftText])
    tables: list[DraftTable] = Field(default_factory=list[DraftTable])
    figures: list[DraftFigure] = Field(default_factory=list[DraftFigure])
    missing_fact_ids: list[str] = Field(default_factory=list[str])

    @model_validator(mode="after")
    def section_contract(self) -> SectionDraft:
        if self.section not in SECTION_FACTS:
            raise ValueError("draft section is outside chapter 2-3 catalogue")
        if self.status == "missing" and not self.missing_fact_ids:
            raise ValueError("missing draft requires missing fact ids")
        if self.status == "drafted" and self.missing_fact_ids:
            raise ValueError("drafted section cannot list missing fact ids")
        if self.status == "drafted" and not (self.paragraphs or self.tables or self.figures):
            raise ValueError("drafted section needs content")
        return self
