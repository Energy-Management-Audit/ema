"""Mechanical traceability checks of a section draft: every name and number from a token."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from ema.audit.ai_wording import ai_wording
from ema.audit.catalogue_types import PASSAGE_FACTS, fact_key
from ema.audit.draft_schema import DraftText, SectionDraft, citable
from ema.core.review.models import Field

TOKEN = re.compile(r"\{\{f:([a-z][a-z0-9_.:-]*)\}\}")
# A citation names the fact a paraphrase rests on and renders nothing (D1).
CITE = re.compile(r"\{\{c:([a-z][a-z0-9_.:-]*)\}\}")
ANY_TOKEN = re.compile(r"\{\{[fc]:([a-z][a-z0-9_.:-]*)\}\}")
CITE_GAP = re.compile(r"\s*" + CITE.pattern)
NUMBER = re.compile(r"\d")
# Romanian number words, matched on text folded to plain letters so that "două", "doua", "şase"
# and "șase" are one word: a quantity spelled out is a number outside a fact token (D1).
NUMBER_WORD = re.compile(
    r"\b(?:unu|una|doi|doua|trei|patru|cinci|sase|sapte|opt|noua|zece|suta|sute|mie|mii"
    r"|milion|milioane|(?:un|doi|doua|trei|pai|patru|cinci|sai|sapte|opt|noua)(?:sprezece|zeci))\b"
)
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
    return bool(TOKEN.search(text)) and not re.sub(r"[\s.,;:!?]", "", ANY_TOKEN.sub("", text))


def folded(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char)
    ).casefold()


def literal_number(plain: str) -> bool:
    """Text outside fact tokens that states a quantity: a digit or a Romanian number word."""
    return bool(NUMBER.search(plain) or NUMBER_WORD.search(folded(plain)))


def citable_fact(section: str, key: str, fact: Field | None, job: str) -> bool:
    """A fact either token may name: the section's own, found, not rejected, with evidence."""
    return (
        citable(section, key)
        and fact is not None
        and fact.job_id == job
        and fact.presence == "found"
        and fact.review != "rejected"
        and bool(fact.evidence)
    )


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


def texts(draft: SectionDraft) -> list[tuple[str, DraftText]]:
    return [(f"paragraph:{i}", paragraph) for i, paragraph in enumerate(draft.paragraphs)]


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


def check_draft(draft: SectionDraft, facts: dict[str, Field], job: str) -> DraftCheck:
    fatal: list[DraftReview] = []
    review: list[DraftReview] = []
    known_names = {
        unicodedata.normalize("NFKC", str(field.value)).casefold()
        for field in facts.values()
        if field.key.endswith(("company_name", "client_name")) and field.job_id == job
    }
    common = {name.casefold() for name in NAME_COMMON}
    cited = total = 0
    for location, item in texts(draft):
        tokens = set(ANY_TOKEN.findall(item.text))
        plain = ANY_TOKEN.sub("", item.text)
        if tokens != set(item.fact_ids):
            fatal.append(DraftReview("fact_refs", location, "tokens and listed fact ids differ"))
        fatal.extend(
            DraftReview("fact_missing", location, key)
            for key in sorted(tokens | set(item.fact_ids))
            if not citable_fact(draft.section, key, facts.get(key), job)
        )
        if literal_number(plain):
            fatal.append(DraftReview("literal_number", location, "number outside fact reference"))
        resolved = TOKEN.sub(
            lambda match: str(facts[match.group(1)].value) if match.group(1) in facts else "",
            CITE_GAP.sub("", item.text),
        )
        if ai_wording(resolved):
            fatal.append(DraftReview("ai_mention", location, "AI or disclaimer wording"))
        candidates = {
            candidate
            for candidate in (
                *NAME.findall(_sentence_marked(CITE_GAP.sub("", item.text), facts)),
                *ACRONYM.findall(plain),
            )
            if candidate.casefold() not in common
        }
        normal_plain = unicodedata.normalize("NFKC", plain).casefold()
        candidates.update(name for name in known_names if name and name in normal_plain)
        fatal.extend(DraftReview("literal_name", location, name) for name in sorted(candidates))
        for sentence in sentence_parts(item.text, facts):
            total += 1
            if ANY_TOKEN.search(sentence):
                cited += 1
            else:
                # Body text without a fact is filler and goes back to the drafter; a bullet is a
                # label, which the auditor reviews.
                issues = fatal if item.kind == "body" else review
                issues.append(DraftReview("uncited_sentence", location, sentence))
    fatal.extend(_passage_layout(draft))
    for key in draft.missing_fact_ids:
        if not citable(draft.section, key) or (
            key in facts and (facts[key].job_id != job or facts[key].presence == "found")
        ):
            fatal.append(DraftReview("missing_status_invalid", "section", key))
    return DraftCheck(cited / total if total else 0.0, cited, total, tuple(fatal), tuple(review))
