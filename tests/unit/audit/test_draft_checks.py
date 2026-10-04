"""Draft trust boundary: references, missing facts and names (rendering: test_section_body)."""

import pytest

from ema.audit.chapter_tables_data import FAMILIES
from ema.audit.draft_checks import check_draft
from ema.audit.draft_schema import DraftText, SectionDraft, citable
from ema.core.review.models import Field


def _fact(key: str, value: str | int, kind: str = "text") -> Field:
    return Field(
        id=key,
        job_id="synthetic",
        key=key,
        label=key,
        value_type=kind,
        value=value,
        state="supplied",
        presence="found",
        evidence=["synthetic-evidence"],
    )


def _draft(text: str, ids: list[str], section: str = "ch2.date_generale") -> SectionDraft:
    return SectionDraft(
        section=section,
        status="drafted",
        paragraphs=[DraftText(text=text, fact_ids=ids)],
    )


def test_rejects_literal_number_name_ai_and_unknown_fact() -> None:
    facts = {"audit.company_name": _fact("audit.company_name", "Atelier Exemplu")}
    for text, ids, code in (
        (
            "Societatea {{f:audit.company_name}} are 500 angajați.",
            ["audit.company_name"],
            "literal_number",
        ),
        ("Societatea Inventata are sediul aici.", [], "literal_name"),
        (
            "Societatea {{f:audit.company_name}} folosește un algoritm AI.",
            ["audit.company_name"],
            "ai_mention",
        ),
        ("Societatea {{f:audit.cui}} este aici.", ["audit.cui"], "fact_missing"),
    ):
        assert code in {
            issue.code for issue in check_draft(_draft(text, ids), facts, "synthetic").fatal
        }


def test_sentence_start_after_a_sentence_fact_is_not_a_name() -> None:
    facts = {
        "audit.company_name": _fact("audit.company_name", "Atelier Exemplu"),
        "audit.business_activity": _fact("audit.business_activity", "Produce piese turnate."),
    }
    names = {
        issue.detail
        for issue in check_draft(
            _draft(
                "Dotările sunt noi. {{f:audit.business_activity}} Aceste etape sunt continue. "
                "Societatea {{f:audit.company_name}} Inventata are sediul aici.",
                ["audit.business_activity", "audit.company_name"],
            ),
            facts,
            "synthetic",
        ).fatal
        if issue.code == "literal_name"
    }
    assert names == {"Inventata"}


@pytest.mark.parametrize(
    ("value", "text", "names"),
    [
        ("„Produce piese.”  ", "{{f:audit.business_activity}} Aceste etape continuă.", set()),
        ("Produce piese.", "{{f:audit.business_activity}}Aceste etape continuă.", set()),
        ("Produce piese.", "{{f:audit.business_activity}}  Aceste etape continuă.", set()),
        ("Produce piese.", "{{f:audit.business_activity}} ACME are sediul aici.", {"ACME"}),
        (
            "piese turnate",
            "Societatea produce {{f:audit.business_activity}} Inventata.",
            {"Inventata"},
        ),
        (
            "piese",
            "Producţia include {{f:audit.business_activity}} şi Aceştia Inventati.",
            {"Aceştia Inventati"},
        ),
        ("Produce piese.", "{{f:audit.business_activity}} ANRE avizează. CUI și CAEN apar.", set()),
    ],
)
def test_name_rule_at_fact_boundaries(value: str, text: str, names: set[str]) -> None:
    facts = {"audit.business_activity": _fact("audit.business_activity", value)}
    found = {
        (issue.code, issue.detail)
        for issue in check_draft(
            _draft(text, ["audit.business_activity"], "ch2.activitate"), facts, "synthetic"
        ).fatal
        if issue.code == "literal_name"
    }
    assert found == {("literal_name", name) for name in names}


def test_an_uncited_body_sentence_is_fatal_filler() -> None:
    facts = {"audit.company_name": _fact("audit.company_name", "Atelier Exemplu")}
    draft = _draft(
        "Societatea {{f:audit.company_name}} produce bunuri. Este modernă.", ["audit.company_name"]
    )
    checked = check_draft(draft, facts, "synthetic")
    assert checked.coverage == 0.5
    assert [(issue.code, issue.location, issue.detail) for issue in checked.fatal] == [
        ("uncited_sentence", "paragraph:0", "Este modernă.")
    ]
    assert checked.review == ()


@pytest.mark.parametrize(
    "text",
    [
        "Sediul este pe str. {{f:audit.company_name}}.",
        "Clădirea de la nr. {{f:audit.company_name}} este în jud. {{f:audit.company_name}}.",
    ],
)
def test_an_abbreviation_does_not_end_a_sentence(text: str) -> None:
    facts = {"audit.company_name": _fact("audit.company_name", "Atelier Exemplu")}
    checked = check_draft(_draft(text, ["audit.company_name"]), facts, "synthetic")
    assert (checked.cited_sentences, checked.total_sentences, checked.fatal) == (1, 1, ())


def test_an_uncited_bullet_is_reviewed_not_fatal() -> None:
    facts = {"audit.company_name": _fact("audit.company_name", "Atelier Exemplu")}
    draft = SectionDraft(
        section="ch2.date_generale",
        status="drafted",
        paragraphs=[DraftText(text="ambalare şi depozitare", kind="bullet")],
    )
    checked = check_draft(draft, facts, "synthetic")
    assert checked.fatal == ()
    assert [(issue.code, issue.location) for issue in checked.review] == [
        ("uncited_sentence", "paragraph:0")
    ]


def test_a_numbered_passage_is_a_fact_of_its_section() -> None:
    passage = "Etapa de vopsire începe cu degresarea pieselor."
    facts = {
        key: _fact(key, passage)
        for key in ("audit.process_sections", "audit.process_sections.2", "audit.history.2")
    }
    ok = SectionDraft(
        section="ch3.process",
        status="drafted",
        paragraphs=[
            DraftText(text=f"{{{{f:{key}}}}}", fact_ids=[key])
            for key in ("audit.process_sections", "audit.process_sections.2")
        ],
    )
    assert check_draft(ok, facts, "synthetic").fatal == ()
    foreign = _draft("{{f:audit.history.2}}", ["audit.history.2"], "ch3.process")
    assert [issue.code for issue in check_draft(foreign, facts, "synthetic").fatal] == [
        "fact_missing"
    ]


FACTS = {
    "audit.company_name": _fact("audit.company_name", "Atelier Exemplu"),
    "audit.employees": _fact("audit.employees", 85, "number"),
}


def _codes(text: str, ids: list[str], facts: dict[str, Field] = FACTS) -> set[str]:
    return {issue.code for issue in check_draft(_draft(text, ids), facts, "synthetic").fatal}


def test_a_paraphrase_with_a_citation_passes() -> None:
    text = "Societatea are personal propriu de producţie {{c:audit.employees}}."
    checked = check_draft(_draft(text, ["audit.employees"]), FACTS, "synthetic")
    assert (checked.fatal, checked.cited_sentences, checked.total_sentences) == ((), 1, 1)


def test_a_number_outside_a_value_token_fails_even_when_a_cited_fact_holds_it() -> None:
    assert "literal_number" in _codes(
        "Firma are 500 angajaţi {{c:audit.employees}}.", ["audit.employees"]
    )
    # D1: the cited fact holds 85, still only a value token may print it.
    assert "literal_number" in _codes(
        "Firma are 85 angajaţi {{c:audit.employees}}.", ["audit.employees"]
    )


def test_a_name_prints_only_from_a_value_token() -> None:
    assert (
        _codes("Societatea {{f:audit.company_name}} produce ambalaje.", ["audit.company_name"])
        == set()
    )
    # D1: a name the cited fact holds is still a literal name outside its value token.
    assert "literal_name" in _codes(
        "Firma Atelier Exemplu produce ambalaje {{c:audit.company_name}}.", ["audit.company_name"]
    )


@pytest.mark.parametrize(
    "word",
    ["două", "doua", "şase", "șase", "Trei", "zece", "sute", "mii", "douăzeci", "unsprezece"],
)
def test_a_romanian_number_word_is_a_literal_number(word: str) -> None:
    text = f"Linia are {word} posturi de lucru {{{{c:audit.employees}}}}."
    assert "literal_number" in _codes(text, ["audit.employees"])


@pytest.mark.parametrize("word", ["optim", "unitatea", "trecut", "operare", "cincinal", "noul"])
def test_a_word_that_holds_a_number_word_is_not_one(word: str) -> None:
    text = f"Societatea are un regim {word} de lucru {{{{c:audit.employees}}}}."
    assert "literal_number" not in _codes(text, ["audit.employees"])


@pytest.mark.parametrize(
    "change", [{"review": "rejected"}, {"presence": "missing"}, {"evidence": []}]
)
def test_a_rejected_or_unfound_fact_is_citable_by_neither_token(change: dict[str, object]) -> None:
    facts = {"audit.employees": FACTS["audit.employees"].model_copy(update=change)}
    for token in ("c", "f"):
        text = f"Societatea are personal {{{{{token}:audit.employees}}}}."
        assert "fact_missing" in _codes(text, ["audit.employees"], facts)


def test_listed_ids_include_citations() -> None:
    text = "Societatea are personal {{c:audit.employees}}."
    assert "fact_refs" in _codes(text, [])


@pytest.mark.parametrize(
    ("section", "key", "allowed"),
    [
        ("ch3.electricitate", "audit.transformer.1.putere_nominala", True),
        ("ch3.apa", "audit.transformer.1.putere_nominala", False),
        ("ch3.equipment", "audit.equipment_row.2.name", True),
        ("ch3.equipment", "audit.equipment_row.2.process", True),
        ("ch3.gaz", "audit.equipment_row.2.name", True),
        ("ch3.gaz", "audit.equipment_row.2.resource", True),
        ("ch3.apa", "audit.equipment_row.2.name", False),
        # The equipment table prints these; the prose refers to it (D4).
        ("ch3.equipment", "audit.equipment_row.2.count", False),
        ("ch3.gaz", "audit.equipment_row.2.power", False),
        ("ch3.gaz", "audit.heating.2", True),
    ],
)
def test_necesar_rows_are_described_in_their_ch3_section(
    section: str, key: str, allowed: bool
) -> None:
    assert citable(section, key) is allowed


def test_the_render_reads_the_transformer_rows_a_draft_cites() -> None:
    assert "audit.transformer." in FAMILIES
