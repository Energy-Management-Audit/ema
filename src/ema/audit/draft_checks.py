"""Mechanical traceability checks and the separate qualitative support pass."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from pydantic import Field as ModelField

from ema.audit.ai_wording import ai_wording
from ema.audit.draft_schema import SECTION_FACTS, DraftText, SectionDraft
from ema.core.errors import EmaError
from ema.core.llm.agent import AgentContext
from ema.core.llm.structured import complete_json
from ema.core.review.models import Field

TOKEN = re.compile(r"\{\{f:([a-z][a-z0-9_.:-]*)\}\}")
NUMBER = re.compile(r"\d")
NAME = re.compile(
    r"(?<![.!?]\s)(?<!\w)[A-ZĂÂÎȘȚ][A-Za-zĂÂÎȘȚăâîșț]{1,}(?:\s+[A-ZĂÂÎȘȚ][A-Za-zĂÂÎȘȚăâîșț]{2,})*"
)
NAME_COMMON = frozenset(
    {
        "Societatea",
        "Compania",
        "Figura",
        "Tabelul",
        "Conform",
        "Fluxul",
        "Procesul",
        "Echipamentele",
        "Amplasamentul",
        "Date",
        "În",
        "Pentru",
        "Din",
        "Aceasta",
        "Etapa",
    }
)


@dataclass(frozen=True)
class DraftReview:
    code: str
    location: str
    detail: str


@dataclass(frozen=True)
class DraftCheck:
    coverage: float
    cited_sentences: int
    total_sentences: int
    fatal: tuple[DraftReview, ...]
    review: tuple[DraftReview, ...]


def _texts(draft: SectionDraft) -> list[tuple[str, DraftText]]:
    result = [(f"paragraph:{i}", paragraph) for i, paragraph in enumerate(draft.paragraphs)]
    for table_index, table in enumerate(draft.tables):
        result.append((f"table:{table_index}:caption", table.caption))
        result.extend(
            (f"table:{table_index}:{row_index}:{cell_index}", cell)
            for row_index, row in enumerate(table.rows)
            for cell_index, cell in enumerate(row)
        )
    result.extend((f"figure:{i}:caption", figure.caption) for i, figure in enumerate(draft.figures))
    return result


def check_draft(  # noqa: C901, PLR0912
    draft: SectionDraft, facts: dict[str, Field], job: str
) -> DraftCheck:
    fatal: list[DraftReview] = []
    review: list[DraftReview] = []
    allowed = SECTION_FACTS[draft.section]
    known_names = {
        unicodedata.normalize("NFKC", str(field.value)).casefold()
        for field in facts.values()
        if field.key.endswith(("company_name", "client_name")) and field.job_id == job
    }
    cited = total = 0
    for location, item in _texts(draft):
        tokens = set(TOKEN.findall(item.text))
        plain = TOKEN.sub("", item.text)
        declared = set(item.fact_ids)
        if tokens != declared:
            fatal.append(DraftReview("fact_refs", location, "tokens and listed fact ids differ"))
        for key in tokens | declared:
            fact = facts.get(key)
            if (
                key not in allowed
                or fact is None
                or fact.job_id != job
                or fact.presence != "found"
                or not fact.evidence
            ):
                fatal.append(DraftReview("fact_missing", location, key))
        if NUMBER.search(plain):
            fatal.append(DraftReview("literal_number", location, "number outside fact reference"))
        resolved = TOKEN.sub(
            lambda match: str(facts[match.group(1)].value) if match.group(1) in facts else "",
            item.text,
        )
        if ai_wording(resolved):
            fatal.append(DraftReview("ai_mention", location, "AI or disclaimer wording"))
        common = {name.casefold() for name in NAME_COMMON}
        candidates = {
            candidate for candidate in NAME.findall(plain) if candidate.casefold() not in common
        }
        normal_plain = unicodedata.normalize("NFKC", plain).casefold()
        candidates.update(name for name in known_names if name and name in normal_plain)
        for candidate in sorted(candidates):
            fatal.append(DraftReview("literal_name", location, candidate))
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", item.text) if part.strip()]
        for sentence in sentences:
            total += 1
            if TOKEN.search(sentence):
                cited += 1
            else:
                review.append(DraftReview("uncited_sentence", location, sentence))
    for figure_index, figure in enumerate(draft.figures):
        fact = facts.get(figure.fact_id)
        if (
            figure.fact_id not in allowed
            or fact is None
            or fact.job_id != job
            or fact.presence != "found"
            or not fact.evidence
        ):
            fatal.append(
                DraftReview("figure_fact_missing", f"figure:{figure_index}", figure.fact_id)
            )
    review.extend(
        DraftReview("unrendered_table", f"table:{index}", "S8 table slots required")
        for index in range(len(draft.tables))
    )
    review.extend(
        DraftReview("unrendered_figure", f"figure:{index}", "S8 figure slots required")
        for index in range(len(draft.figures))
    )
    for key in draft.missing_fact_ids:
        if key not in allowed or (
            key in facts and (facts[key].job_id != job or facts[key].presence == "found")
        ):
            fatal.append(DraftReview("missing_status_invalid", "section", key))
    return DraftCheck(cited / total if total else 0.0, cited, total, tuple(fatal), tuple(review))


class SupportFlag(BaseModel):
    location: str
    sentence: str
    reason: str


class SupportResult(BaseModel):
    flags: list[SupportFlag] = ModelField(default_factory=list[SupportFlag])


SUPPORT_PROMPT = (
    "Flag every sentence whose cited facts do not support its claim, including qualitative "
    "overstatement. Return locations, exact sentences and reasons. Do not infer missing facts."
)


def support_pass(
    context: AgentContext, draft: SectionDraft, facts: dict[str, Field]
) -> tuple[DraftReview, ...]:
    items = _texts(draft)
    request: list[dict[str, Any]] = []
    for location, item in items:
        request.append(
            {
                "location": location,
                "text": item.text,
                "facts": {key: str(facts[key].value) for key in item.fact_ids if key in facts},
            }
        )
    result = complete_json(
        context, SupportResult, SUPPORT_PROMPT, json.dumps(request, ensure_ascii=False)
    )
    known = {location: item.text for location, item in items}
    if any(
        flag.location not in known or flag.sentence not in known[flag.location]
        for flag in result.flags
    ):
        raise EmaError(
            "support_invalid", "Verificarea afirmaţiilor a returnat o poziţie invalidă.", ""
        )
    return tuple(DraftReview("unsupported", flag.location, flag.reason) for flag in result.flags)
