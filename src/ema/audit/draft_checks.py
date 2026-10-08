"""Mechanical traceability checks of a section draft: every number from a token, every client
name from a token or a fact the text cites; general sentences need no citation (#143)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from ema.audit.ai_wording import ai_wording
from ema.audit.catalogue_types import PASSAGE_FACTS, fact_key
from ema.audit.draft_schema import DraftText, SectionDraft, citable
from ema.audit.research_quote import in_quote
from ema.core.review.models import Field

TOKEN = re.compile(r"\{\{f:([a-z][a-z0-9_.:-]*)\}\}")
# A citation names the fact a paraphrase rests on and renders nothing (D1).
CITE = re.compile(r"\{\{c:([a-z][a-z0-9_.:-]*)\}\}")
ANY_TOKEN = re.compile(r"\{\{[fc]:([a-z][a-z0-9_.:-]*)\}\}")
CITE_GAP = re.compile(r"\s*" + CITE.pattern)
NUMBER = re.compile(r"\d")
# Romanian number words, matched on text folded to plain letters so that "două", "doua", "şase"
# and "șase" are one word: a quantity spelled out is a number outside a fact token (D1).
# Ordinals from the second up and fractions state an order or a share as much as a cardinal
# does; "primul", "prima" and "ultimul" stay free for "în primul rând" and ordered stages.
NUMBER_WORD = re.compile(
    r"\b(?:zero|unu|una|doi|doua|trei|patru|cinci|sase|sapte|opt|noua|zece|suta|sute|mie|mii"
    r"|milion|milioane|(?:un|doi|doua|trei|pai|patru|cinci|sai|sapte|opt|noua)(?:sprezece|zeci)"
    r"|doilea|treilea|patrulea|cincilea|saselea|saptelea|optulea|noualea|zecelea"
    r"|treia|patra|cincea|sasea|saptea|zecea|a opta(?!\s+pentru)"
    r"|jumatat(?:e|ea|ii|i|ile|ilor)|treim(?:e|ea|ii|i|ile|ilor)|sfert(?:ul|ului|uri|urile|urilor)?"
    r"|dubl(?:u|ul|ului|a|e|ei|i|ii|ilor)|tripl(?:u|ul|ului|a|e|ei|i|ii|ilor))\b"
)
UPPER = "A-ZĂÂÎȘȚŞŢ"
LOWER = "a-zăâîșțşţ"
NAME = re.compile(
    rf"(?<![.!?]\s)(?<!\w)[{UPPER}][{UPPER}{LOWER}]{{1,}}(?:\s+[{UPPER}][{UPPER}{LOWER}]{{2,}})*"
)
ACRONYM = re.compile(rf"(?<!\w)[{UPPER}]{{2,}}(?!\w)")
SENTENCE_WORD = re.compile(rf"[{UPPER}][{LOWER}]+(?!\w)")
CEDILLAS = str.maketrans("şţ", "st")
# The regulatory references a general sentence may print in figures (D3), each only in the
# words that make it a reference: the law, the standard, or the threshold.
REFERENCE_NUMBERS = ("121/2014", "50001", "16247", "1.000 tep", "1000 tep")
_THRESHOLD = (
    r"(?i:\b(?:prag|pragul|sub|peste|depășește|depăşeşte|inferior|superior)\b)"
    r"(?:\s+[^\s\d]+){0,3}\s+"
)
_REFERENCE_CONTEXT = {
    "121/2014": r"\b[Ll]eg(?:ea|ii)\s+(?:nr\.\s*)?",
    "50001": r"\bISO\s+",
    "16247": r"\bEN\s+",
    "1.000 tep": _THRESHOLD,
    "1000 tep": _THRESHOLD,
}
REFERENCES = tuple(
    re.compile(
        f"({_REFERENCE_CONTEXT[number]}){re.escape(number)}"
        + (r"(?:-\d+)?" if number == "16247" else "")
        + r"(?![\w/]|[.,]\d)"
    )
    for number in REFERENCE_NUMBERS
)
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
        "SEN",
        "CAEN",
        "CUI",
        "SRL",
        "SA",
        "GJ",
        "TEP",
        "MWh",
        "kWh",
        # The law, standards and institutions a general sentence names (D3); a candidate inside
        # one of these phrases, as "EN ISO" or "Energetic Național", is part of it.
        "Legea",
        "Legii",
        "SR EN ISO",
        "Sistemul Energetic Național",
        "Ministerul Energiei",
        "Ministerului Energiei",
    }
) | frozenset(
    # Generic technical and institutional terms only, never a client, supplier or site: a
    # general sentence may write these in capitals.
    {
        "LED",
        "GPL",
        "UE",
        "Uniunea Europeană",
        "HVAC",
        "CTA",
        "PT",
        "MT",
        "JT",
        "IT",
        "SCADA",
        "PLC",
        "AC",
        "CC",
        "CET",
        "CHP",
        "PIF",
        "kWp",
        "VFD",
        "TGD",
        "TD",
        "BMS",
        "UPS",
        "PCS",
        "COP",
        "EER",
        "SCOP",
        "SEER",
        "NOx",
        "CO2",
        "CO₂",
    }
)
# A capitalised word before a legal form is a company's name, wherever it stands.
LEGAL_NAME = re.compile(
    rf"(?<!\w)[{UPPER}][{UPPER}{LOWER}-]*(?=\s+(?:S\.R\.L\.|S\.A\.|SRL|SA)(?!\w))"
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


def traced(text: str) -> str:
    """Text as a name is matched against a cited value: folded, cedillas plain, spaces single."""
    return " ".join(folded(text).translate(CEDILLAS).split())


COMMON = tuple(traced(name) for name in NAME_COMMON)


def literal_number(plain: str) -> bool:
    """Text outside fact tokens that states a quantity: a digit or a Romanian number word,
    a regulatory reference aside (D3)."""
    for reference in REFERENCES:
        plain = reference.sub(r"\1 ", plain)
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


def _names(sentence: str, facts: dict[str, Field], known: set[str]) -> dict[str, bool]:
    """The sentence's name candidates, once each, as written where the text has them, and
    whether each has a proper name's shape: several capitalised words, an acronym, or a word
    before a legal form. Generic terms are not candidates."""
    plain = ANY_TOKEN.sub("", sentence)
    found: dict[str, tuple[str, bool]] = {}
    for name, shaped in (
        *(
            (name, " " in name)
            for name in NAME.findall(_sentence_marked(CITE_GAP.sub("", sentence), facts))
        ),
        *((name, True) for name in ACRONYM.findall(plain)),
        *((name, True) for name in LEGAL_NAME.findall(plain)),
        *((name, False) for name in sorted(known) if in_quote(name, traced(plain))),
    ):
        first, before = found.get(traced(name), (name, False))
        found[traced(name)] = (first, shaped or before)
    return {
        name: shaped
        for key, (name, shaped) in found.items()
        if not any(in_quote(key, common) for common in COMMON)
    }


def _passage(key: str) -> bool:
    """A key of a passage fact, its first passage numbered or not."""
    base, _, number = key.rpartition(".")
    return fact_key(key) in PASSAGE_FACTS or (base in PASSAGE_FACTS and number.isdigit())


def _missing_item(
    section: str, location: str, item: DraftText, facts: dict[str, Field], job: str
) -> list[DraftReview]:
    """A missing item has no text and names the section's keys it lacks, none with a usable
    value; any other item names none (#163 D2)."""
    if item.kind != "missing":
        return [DraftReview("missing_item_invalid", location, key) for key in item.missing_fact_ids]
    issues = [
        DraftReview("missing_item_invalid", location, key)
        for key in item.missing_fact_ids
        if not citable(section, key) or citable_fact(section, key, facts.get(key), job)
    ]
    if item.text.strip() or not item.missing_fact_ids:
        issues.append(DraftReview("missing_item_invalid", location, "text or keys"))
    return issues


def check_draft(draft: SectionDraft, facts: dict[str, Field], job: str) -> DraftCheck:
    fatal: list[DraftReview] = []
    known = {
        traced(str(field.value))
        for field in facts.values()
        if field.key.endswith(("company_name", "client_name")) and field.job_id == job
    } - {""}
    # Any value the section is offered is client data: an uncited sentence may not name it.
    offered = [traced(str(field.value)) for field in facts.values() if field.value is not None]
    cited = total = 0
    for location, item in texts(draft):
        tokens = set(ANY_TOKEN.findall(item.text))
        if tokens != set(item.fact_ids):
            fatal.append(DraftReview("fact_refs", location, "tokens and listed fact ids differ"))
        fatal.extend(
            DraftReview("fact_missing", location, key)
            for key in sorted(tokens | set(item.fact_ids))
            if not citable_fact(draft.section, key, facts.get(key), job)
        )
        # A passage is rewritten in her register and cited, never printed as the source has it.
        fatal.extend(
            DraftReview("passage_verbatim", location, key)
            for key in sorted(set(TOKEN.findall(item.text)))
            if _passage(key)
        )
        if literal_number(ANY_TOKEN.sub("", item.text)):
            fatal.append(DraftReview("literal_number", location, "number outside fact reference"))
        resolved = TOKEN.sub(
            lambda match: str(facts[match.group(1)].value) if match.group(1) in facts else "",
            CITE_GAP.sub("", item.text),
        )
        if ai_wording(resolved):
            fatal.append(DraftReview("ai_mention", location, "AI or disclaimer wording"))
        # A name the item's cited facts hold, as whole words, is traceable whether quoted or
        # paraphrased (#137).
        values = [
            traced(str(facts[key].value))
            for key in tokens
            if citable_fact(draft.section, key, facts.get(key), job)
        ]
        names: set[str] = set()
        for sentence in sentence_parts(item.text, facts):
            total += 1
            if ANY_TOKEN.search(sentence):
                cited += 1
                names |= {
                    name
                    for name in _names(sentence, facts, known)
                    if not any(in_quote(traced(name), value) for value in values)
                }
            else:
                # A general sentence names generic terms freely; a client's name, or anything
                # shaped like a proper name, fails whatever the support pass would say.
                names |= {
                    name
                    for name, shaped in _names(sentence, facts, known).items()
                    if shaped or any(in_quote(traced(name), value) for value in (*known, *offered))
                }
        fatal.extend(DraftReview("literal_name", location, name) for name in sorted(names))
        fatal.extend(_missing_item(draft.section, location, item, facts, job))
    if draft.status == "drafted" and not any(
        citable_fact(draft.section, key, field, job) for key, field in facts.items()
    ):
        # General text alone does not make a section (v5 rule 16).
        fatal.append(DraftReview("status_invalid", "section", "no usable fact"))
    for key in draft.missing_fact_ids:
        if not citable(draft.section, key) or (
            key in facts and (facts[key].job_id != job or facts[key].presence == "found")
        ):
            fatal.append(DraftReview("missing_status_invalid", "section", key))
    return DraftCheck(cited / total if total else 0.0, cited, total, tuple(fatal), ())
