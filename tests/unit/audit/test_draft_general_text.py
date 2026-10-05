"""Prompt v5 checks (#143): general sentences, passages rewritten, regulatory references."""

import pytest
from tests.unit.audit.test_draft_checks import FACTS, _draft, _fact

from ema.audit.draft_checks import REFERENCE_NUMBERS, check_draft
from ema.core.review.models import Field


def _issues(
    text: str, ids: list[str], facts: dict[str, Field] = FACTS, section: str = "ch2.date_generale"
) -> list[tuple[str, str]]:
    checked = check_draft(_draft(text, ids, section), facts, "synthetic")
    return [(issue.code, issue.detail) for issue in checked.fatal]


@pytest.mark.parametrize("key", ["audit.history", "audit.history.1", "audit.history.2"])
def test_a_passage_printed_from_its_value_token_is_verbatim(key: str) -> None:
    facts = {key: _fact(key, "Fabrica a fost înfiinţată de asociaţi.")}
    assert ("passage_verbatim", key) in _issues(f"{{{{f:{key}}}}}", [key], facts, "ch2.istorie")


def test_a_passage_rewritten_and_cited_passes() -> None:
    key = "audit.history.2"
    facts = {key: _fact(key, "Fabrica a fost infiintata de asociati.")}
    rewritten = f"Fabrica a fost înființată de asociați {{{{c:{key}}}}}."
    assert _issues(rewritten, [key], facts, "ch2.istorie") == []


def test_the_reference_numbers_are_the_plan_literals() -> None:
    assert REFERENCE_NUMBERS == ("121/2014", "50001", "16247", "1.000 tep", "1000 tep")


@pytest.mark.parametrize(
    "text",
    [
        "Auditul energetic este obligatoriu conform Legii nr. 121/2014.",
        "Sistemul de management al energiei urmează SR EN ISO 50001.",
        "Auditul se desfăşoară după SR EN 16247.",
        "Obligaţia se aplică peste pragul de 1.000 tep.",
        "Obligaţia se aplică peste pragul de 1000 tep.",
        "Auditul se desfăşoară după SR EN 16247-1.",
        "Consumul este sub pragul legal de 1.000 tep.",
    ],
)
def test_a_regulatory_reference_is_not_a_literal_number(text: str) -> None:
    assert _issues(text, []) == []


@pytest.mark.parametrize(
    "text",
    [
        "Linia funcţionează din 1998.",
        "Societatea are o sută de utilaje.",
        "Auditul urmează Legea nr. 121/20145.",
        # A reference number outside its reference is a quantity (fix round 1).
        "Societatea are 50001 kWh consumați.",
        "Firma are 121/2014 angajați.",
        "Societatea consumă anual 1000 tep.",
        "Consumul societății este de 1.000 tep.",
        "Auditul urmează standardul 16247.",
    ],
)
def test_a_number_in_an_uncited_sentence_fails(text: str) -> None:
    assert ("literal_number", "number outside fact reference") in _issues(text, [])


def test_an_uncited_sentence_naming_the_client_fails() -> None:
    assert _issues("Producţia este asigurată de Atelier Exemplu.", []) == [
        ("literal_name", "Atelier Exemplu")
    ]


def test_an_uncited_sentence_naming_a_value_offered_to_the_section_fails() -> None:
    key = "audit.electricity_supply"
    facts = {key: _fact(key, "Energia este livrată de Furnizorul Exemplu Energie.")}
    issues = _issues(
        "Energia electrică vine de la Exemplu Energie.", [], facts, "ch3.electricitate"
    )
    assert issues == [("literal_name", "Exemplu Energie")]


@pytest.mark.parametrize(
    "text",
    [
        "Raportul de audit se transmite la ANRE.",
        "Sistemul de management al energiei urmează SR EN ISO 50001.",
        "Energia electrică provine din Sistemul Energetic Național.",
        "Sistemul Energetic Național asigură alimentarea consumatorilor.",
        "Politica energetică este coordonată de Ministerul Energiei şi de SEN.",
    ],
)
def test_institutions_and_standards_pass_in_any_sentence(text: str) -> None:
    assert _issues(text, []) == []
    cited = text.rstrip(".") + " {{c:audit.employees}}."
    assert _issues(cited, ["audit.employees"]) == []


def test_a_cited_sentence_still_names_only_what_its_facts_hold() -> None:
    text = "Societatea {{f:audit.company_name}} colaborează cu Cooperativa Meşteşugarilor."
    assert _issues(text, ["audit.company_name"]) == [("literal_name", "Cooperativa Meşteşugarilor")]
