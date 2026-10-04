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
from ema.audit.catalogue_types import PASSAGE_FACTS, fact_key
from ema.audit.draft_schema import SECTION_FACTS, DraftText, SectionDraft
from ema.core.errors import EmaError
from ema.core.llm.agent import AgentContext
from ema.core.llm.structured import complete_json
from ema.core.review.models import Field

TOKEN = re.compile(r"\{\{f:([a-z][a-z0-9_.:-]*)\}\}")
NUMBER = re.compile(r"\d")
UPPER = "A-ZĂÂÎȘȚŞŢ"
LOWER = "a-zăâîșțşţ"
NAME = re.compile(
    rf"(?<![.!?]\s)(?<!\w)[{UPPER}][{UPPER}{LOWER}]{{1,}}(?:\s+[{UPPER}][{UPPER}{LOWER}]{{2,}})*"
)
ACRONYM = re.compile(rf"(?<!\w)[{UPPER}]{{2,}}(?!\w)")
SENTENCE_WORD = re.compile(rf"[{UPPER}][{LOWER}]+(?!\w)")
FACT_GAP = re.compile(TOKEN.pattern + r"(\s*)")
# A sentence does not end after an address or legal abbreviation, as in "nr. {{f:...}}", or
# after an initial, as in "S.R.L.".
ABBREVIATIONS = ("nr", "str", "jud", "loc", "com", "bl", "ap", "art", "alin", "lit", "pct", "tel")
SENTENCE_END = re.compile(
    r"(?i)(?<=[.!?])"
    + "".join(rf"(?<!\b{word}\.)" for word in ABBREVIATIONS)
    + r"(?<!\b[^\W\d_]\.)\s+"
)
FACT_BREAK = re.compile(r"(" + TOKEN.pattern + r")\s+")
# A value such as "Firma Exemplu S.R.L." or "nr." stops on an abbreviation, not a sentence end.
ABBREVIATED_END = re.compile(
    rf"(?i)(?:(?<![^\s.])(?:[{UPPER}{LOWER}]\.)+|\b(?:{'|'.join(ABBREVIATIONS)})\.)$"
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
        # Regulator, register and legal-form acronyms and units an audit uses as plain words.
        "ANRE",
        "CAEN",
        "CUI",
        "SRL",
        "SA",
        "GJ",
        "TEP",
        "MWh",
        "kWh",
    }
)


def _ends_sentence(key: str, fact: Field | None) -> bool:
    """A passage ends a sentence; a short value does only when its stop is not an abbreviation."""
    value = "" if fact is None else str(fact.value).rstrip().rstrip("\"'”’»").rstrip()
    if not value.endswith((".", "!", "?")):
        return False
    return fact_key(key) in PASSAGE_FACTS or not ABBREVIATED_END.search(value)


def sentence_parts(text: str, facts: dict[str, Field]) -> list[str]:
    """The sentences of a draft text, with their fact references, as the checks see them.

    A stop ends a sentence unless it closes an abbreviation; a reference whose value ends a
    sentence, as a passage, ends one too. Rendering splits with this same rule, so a flag on one
    sentence never reaches its neighbour.
    """
    gaps = [(match.start(), match.end()) for match in SENTENCE_END.finditer(text)]
    gaps.extend(
        (match.end(1), match.end())
        for match in FACT_BREAK.finditer(text)
        if _ends_sentence(match.group(2), facts.get(match.group(2)))
    )
    parts: list[str] = []
    start = 0
    for gap_start, gap_end in sorted(set(gaps)):
        if gap_start >= start:
            parts.append(text[start:gap_start])
            start = gap_end
    parts.append(text[start:])
    return [part.strip() for part in parts if part.strip()]


def token_only(text: str) -> bool:
    """Text that is nothing but fact references, as a passage paragraph: the source speaks."""
    return bool(TOKEN.search(text)) and not re.sub(r"[\s.,;:!?]", "", TOKEN.sub("", text))


def _sentence_marked(text: str, facts: dict[str, Field]) -> str:
    """The text for the name check, without fact references.

    A title-case word that opens the paragraph, or follows a fact whose value ends a sentence,
    starts a sentence, as one after a full stop always did: its capital is not taken for a
    proper name. Acronyms are checked separately, wherever they stand.
    """

    def marker(match: re.Match[str]) -> str:
        return ". " if _ends_sentence(match.group(1), facts.get(match.group(1))) else match.group(2)

    marked = FACT_GAP.sub(marker, text)
    return ". " + marked if SENTENCE_WORD.match(marked) else marked


@dataclass(frozen=True)
class DraftReview:
    code: str
    location: str
    detail: str
    sentence: str | None = None


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


def _passage_number(key: str) -> int:
    """A passage's place among its fact's passages; 0 for a fact that is not a passage."""
    base = fact_key(key)
    if base not in PASSAGE_FACTS:
        return 0
    return 1 if base == key else int(key.rpartition(".")[2])


def _passage_layout(draft: SectionDraft) -> list[DraftReview]:
    """One body paragraph per passage, and a fact's passages in their source order."""
    issues: list[DraftReview] = []
    last: dict[str, int] = {}
    for index, item in enumerate(draft.paragraphs):
        location = f"paragraph:{index}"
        passages = [key for key in TOKEN.findall(item.text) if _passage_number(key)]
        if item.kind == "body" and len(passages) > 1:
            issues.append(DraftReview("passage_paragraph", location, ", ".join(passages)))
        for key in passages:
            number, base = _passage_number(key), fact_key(key)
            if number <= last.get(base, 0):
                issues.append(DraftReview("passage_order", location, key))
            last[base] = max(number, last.get(base, 0))
    return issues


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
                fact_key(key) not in allowed
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
            candidate
            for candidate in (
                *NAME.findall(_sentence_marked(item.text, facts)),
                *ACRONYM.findall(plain),
            )
            if candidate.casefold() not in common
        }
        normal_plain = unicodedata.normalize("NFKC", plain).casefold()
        candidates.update(name for name in known_names if name and name in normal_plain)
        for candidate in sorted(candidates):
            fatal.append(DraftReview("literal_name", location, candidate))
        body = location.startswith("paragraph:") and item.kind == "body"
        for sentence in sentence_parts(item.text, facts):
            total += 1
            if TOKEN.search(sentence):
                cited += 1
            else:
                # Body text without a fact is filler and goes back to the drafter; a bullet,
                # caption or table cell is a label, which the auditor reviews.
                issues = fatal if body else review
                issues.append(DraftReview("uncited_sentence", location, sentence))
    fatal.extend(_passage_layout(draft))
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
        DraftReview("unrendered_figure", f"figure:{index}", "S8 figure slots required")
        for index in range(len(draft.figures))
    )
    for key in draft.missing_fact_ids:
        if fact_key(key) not in allowed or (
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


def _support_text(text: str) -> str:
    return " ".join(text.split()).rstrip(".!?").rstrip()


def support_pass(
    context: AgentContext, draft: SectionDraft, facts: dict[str, Field]
) -> tuple[DraftReview, ...]:
    items = _texts(draft)
    # A text that is only fact references, as a passage paragraph, claims nothing of its own.
    request: list[dict[str, Any]] = [
        {
            "location": location,
            "text": item.text,
            "facts": {key: str(facts[key].value) for key in item.fact_ids if key in facts},
        }
        for location, item in items
        if not token_only(item.text)
    ]
    if not request:
        return ()
    result = complete_json(
        context,
        SupportResult,
        SUPPORT_PROMPT,
        json.dumps(request, ensure_ascii=False),
        schema_retries=0,
    )
    known = {location: item.text for location, item in items}
    if any(
        flag.location not in known
        or not _support_text(flag.sentence)
        or _support_text(flag.sentence) not in _support_text(known[flag.location])
        for flag in result.flags
    ):
        raise EmaError(
            "support_invalid", "Verificarea afirmaţiilor a returnat o poziţie invalidă.", ""
        )
    return tuple(
        DraftReview("unsupported", flag.location, flag.reason, flag.sentence)
        for flag in result.flags
        if not token_only(flag.sentence)
    )
