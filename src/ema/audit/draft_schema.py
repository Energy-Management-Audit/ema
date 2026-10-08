"""Structured, fact-addressed drafts for catalogue sections in chapters two and three."""

from __future__ import annotations

from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError, model_validator
from pydantic_core.core_schema import ValidatorFunctionWrapHandler

from ema.audit.catalogue import CATALOGUE
from ema.audit.catalogue_types import fact_key
from ema.audit.read_equipment import EQUIPMENT_ROW, TRANSFORMER

SECTION_FACTS = {
    section.id: frozenset(str(fact) for fact in section.facts)
    for section in CATALOGUE
    if section.chapter in (2, 3) and section.parent is not None
}
# Necesar rows the ch. 3 prose describes from their facts: transformers have no table (#81); an
# equipment row's count and power are printed by the equipment table, so the prose refers to it
# (D4). Gas-fired equipment may also be named in the gas section.
SECTION_FAMILIES = {
    "ch3.electricitate": (TRANSFORMER,),
    "ch3.equipment": (EQUIPMENT_ROW,),
    "ch3.gaz": (EQUIPMENT_ROW,),
}


def _table_quantity(key: str) -> bool:
    return key.startswith(EQUIPMENT_ROW) and key.rpartition(".")[2] in {"count", "power"}


def citable(section: str, key: str) -> bool:
    """A fact key the section's draft may cite, numbered passages and Necesar rows included."""
    if fact_key(key) in SECTION_FACTS.get(section, ()):
        return True
    return key.startswith(SECTION_FAMILIES.get(section, ())) and not _table_quantity(key)


class DraftText(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    fact_ids: list[str] = Field(default_factory=list[str])
    # Ch. 2-3 drafts hold prose only: the deterministic tables are the only tables (D6). A
    # "missing" item keeps the place of a reference paragraph whose client fact Ema lacks: no
    # text, the keys it needs, printed as the marker (#163 D2).
    kind: Literal["body", "bullet", "missing"] = "body"
    # The 3.1.x process unit a ch3.process paragraph describes, from 1; None elsewhere (D3).
    unit: int | None = None
    missing_fact_ids: list[str] = Field(default_factory=list[str])


class SectionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section: str
    status: Literal["drafted", "missing"]
    paragraphs: list[DraftText] = Field(default_factory=list[DraftText])
    missing_fact_ids: list[str] = Field(default_factory=list[str])

    @model_validator(mode="before")
    @classmethod
    def legacy_lists(cls, data: Any) -> Any:
        # A draft stored before v4 lists empty tables and figures; one that has any is redone.
        if isinstance(data, dict):
            data = dict(cast(dict[str, Any], data))
            for name in ("tables", "figures"):
                if data.get(name) == []:
                    del data[name]
        return data

    @model_validator(mode="after")
    def section_contract(self) -> SectionDraft:
        if self.section not in SECTION_FACTS:
            raise ValueError("draft section is outside chapter 2-3 catalogue")
        if self.status == "missing" and not self.missing_fact_ids:
            raise ValueError("missing draft requires missing fact ids")
        if self.status == "drafted" and self.missing_fact_ids:
            raise ValueError("drafted section cannot list missing fact ids")
        if self.status == "drafted" and not self.paragraphs:
            raise ValueError("drafted section needs content")
        return self


class ChapterDraft(BaseModel):
    """One chapter call's answer: a draft per requested section, which the code checks.

    A malformed section does not void the others: it is set aside, by its section id when it has
    one, and treated as omitted.
    """

    model_config = ConfigDict(extra="forbid")

    sections: list[SectionDraft]
    _malformed: list[str] = PrivateAttr(default_factory=list[str])

    @model_validator(mode="wrap")
    @classmethod
    def lenient(cls, data: Any, handler: ValidatorFunctionWrapHandler) -> ChapterDraft:
        malformed: list[str] = []
        if isinstance(data, dict) and isinstance(
            items := cast(dict[str, Any], data).get("sections"), list
        ):
            kept: list[object] = []
            for item in cast(list[object], items):
                try:
                    SectionDraft.model_validate(item)
                    kept.append(item)
                except ValidationError:
                    section = (
                        cast(dict[str, Any], item).get("section")
                        if isinstance(item, dict)
                        else None
                    )
                    malformed.append(str(section))
            data = {**cast(dict[str, Any], data), "sections": kept}
        result = cast(ChapterDraft, handler(data))
        result._malformed = malformed
        return result

    @property
    def malformed(self) -> tuple[str, ...]:
        return tuple(self._malformed)
