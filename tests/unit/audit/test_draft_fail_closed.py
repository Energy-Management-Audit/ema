"""Prompt v5 fix round 1 (#143): numbers, names, status and lists fail closed at the render."""

from pathlib import Path

import pytest
from tests.unit.audit.test_draft_checks import _fact
from tests.unit.audit.test_draft_structured import (
    SECTION,
    SupportProvider,
    _run,
)
from tests.unit.audit.test_section_body import (  # pyright: ignore[reportPrivateUsage]
    FACTS,
    _base,
    _section,
)

from ema.audit.draft_checks import check_draft
from ema.audit.draft_prompt import rule_text
from ema.audit.draft_render import render_section, review_payload
from ema.audit.draft_schema import DraftText, SectionDraft
from ema.audit.draft_support import INTRO_WITHOUT_ITEMS
from ema.core.errors import EmaError


def _render(tmp_path: Path, draft: SectionDraft, facts: dict = FACTS) -> list[str]:  # type: ignore[type-arg]
    output = tmp_path / "out.docx"
    render_section(_base(tmp_path / "base.docx"), output, draft, facts, (), job="synthetic")
    return _section(output)


def _one(text: str, section: str = SECTION) -> SectionDraft:
    return SectionDraft(
        section=section,
        status="drafted",
        paragraphs=[DraftText(text=text, fact_ids=["audit.company_name"])],
    )


@pytest.mark.parametrize(
    "words",
    [
        "zero",
        "o jumătate de",
        "două jumătăți de",
        "jumătatea",
        "o treime de",
        "treimi de",
        "un sfert de",
        "sferturi de",
        "un dublu",
        "o dublă",
        "duble",
        "un triplu",
        "o triplă",
        "al doilea",
        "a doua",
        "celui de-al doilea",
        "al treilea",
        "a treia",
        "al patrulea",
        "a patra",
        "al cincilea",
        "a cincea",
        "al șaselea",
        "al şaselea",
        "a șasea",
        "al șaptelea",
        "a șaptea",
        "al optulea",
        "a opta",
        "al nouălea",
        "a noua",
        "al zecelea",
        "a zecea",
    ],
)
def test_an_ordinal_fraction_or_zero_does_not_render(tmp_path: Path, words: str) -> None:
    draft = _one(f"Societatea {{{{f:audit.company_name}}}} are {words} linie.")
    with pytest.raises(EmaError) as error:
        _render(tmp_path, draft)
    assert error.value.code == "draft_invalid"
    assert "literal_number" in error.value.detail


@pytest.mark.parametrize(
    "words", ["în primul rând", "prima linie", "primele linii", "primii pași", "ultimul pas"]
)
def test_first_and_last_render(tmp_path: Path, words: str) -> None:
    text = f"Societatea {{{{f:audit.company_name}}}} are {words}."
    assert _render(tmp_path, _one(text))[0] == f"Societatea Atelier Exemplu are {words}."


def test_to_opt_is_not_an_ordinal(tmp_path: Path) -> None:
    text = "Societatea {{f:audit.company_name}} poate a opta pentru o linie modernizată."
    assert check_draft(_one(text), FACTS, "synthetic").fatal == ()


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("Energia electrică este livrată de Elnor Energie.", "Elnor Energie"),
        ("Gazul natural este livrat de ELNOR.", "ELNOR"),
        ("Gazul natural este livrat de Elnor S.R.L. prin rețea.", "Elnor"),
        ("Gazul natural este livrat de Elnor SA prin rețea.", "Elnor"),
    ],
)
def test_an_uncited_proper_name_is_fatal_whatever_no_fact_says(text: str, name: str) -> None:
    fatal = check_draft(_one(text), FACTS, "synthetic").fatal
    assert ("literal_name", name) in [(issue.code, issue.detail) for issue in fatal]


def test_an_invented_supplier_labelled_general_and_supported_never_renders(
    tmp_path: Path,
) -> None:
    invented = SectionDraft(
        section=SECTION,
        status="drafted",
        paragraphs=[
            DraftText(
                text="Societatea {{f:audit.company_name}} produce ambalaje.",
                fact_ids=["audit.company_name"],
            ),
            DraftText(text="Energia electrică este livrată de Elnor Energie."),
        ],
    )
    # The support model would wave it through; the check stops it first.
    support = SupportProvider('{"verdicts": []}')
    with pytest.raises(EmaError) as error:
        _run(tmp_path, [invented, invented], support)
    assert error.value.code == "draft_incomplete" and "literal_name" in error.value.detail
    assert support.calls == 0


def test_a_drafted_section_without_a_usable_fact_is_status_invalid() -> None:
    draft = SectionDraft(
        section=SECTION,
        status="drafted",
        paragraphs=[DraftText(text="Auditul energetic analizează consumurile de energie.")],
    )
    rejected = {
        "audit.company_name": FACTS["audit.company_name"].model_copy(update={"review": "rejected"})
    }
    for facts in ({}, rejected):
        fatal = check_draft(draft, facts, "synthetic").fatal
        assert [(issue.code, issue.location) for issue in fatal] == [("status_invalid", "section")]
    assert "textul general singur nu face o secțiune" in rule_text("status_invalid")


INTRO = "Echipamentele utilizate sunt următoarele:"


def test_a_list_introduction_goes_with_its_dropped_items(tmp_path: Path) -> None:
    draft = SectionDraft(
        section=SECTION,
        status="drafted",
        paragraphs=[
            DraftText(
                text=f"Societatea {{{{f:audit.company_name}}}} produce ambalaje. {INTRO}",
                fact_ids=["audit.company_name"],
            ),
            *(
                DraftText(
                    text=f"{item} {{{{c:audit.employees}}}};",
                    fact_ids=["audit.employees"],
                    kind="bullet",
                )
                for item in ("linia de ambalare", "linia de imprimare")
            ),
        ],
    )
    refused = frozenset({(f"{SECTION}:paragraph:1", 0), (f"{SECTION}:paragraph:2", 0)})
    _, _, _, flags = _run(tmp_path / "run", [draft], SupportProvider(refused=refused))
    output = tmp_path / "out.docx"
    facts = FACTS | {"audit.employees": _fact("audit.employees", 85, "number")}
    check = render_section(
        _base(tmp_path / "base.docx"), output, draft, facts, flags, job="synthetic"
    )
    written = _section(output)
    assert written[0] == "Societatea Atelier Exemplu produce ambalaje."
    assert not any(INTRO in text or "linia de" in text for text in written)
    review = review_payload(draft, check, flags)["review"]
    assert [(item["location"], item["detail"], item["sentence"]) for item in review] == [  # type: ignore[index,union-attr]
        ("paragraph:1", "claim", "linia de ambalare {{c:audit.employees}};"),
        ("paragraph:2", "claim", "linia de imprimare {{c:audit.employees}};"),
        ("paragraph:0", INTRO_WITHOUT_ITEMS, INTRO),
    ]


def test_a_stored_draft_printing_a_passage_says_to_redraft(tmp_path: Path) -> None:
    key = "audit.history.2"
    stored = SectionDraft(
        section="ch2.istorie",
        status="drafted",
        paragraphs=[DraftText(text=f"{{{{f:{key}}}}}", fact_ids=[key])],
    )
    facts = {key: _fact(key, "Fabrica a fost înfiinţată de asociaţi.")}
    with pytest.raises(EmaError) as error:
        _render(tmp_path, stored, facts)
    assert error.value.code == "draft_invalid"
    assert f"passage_verbatim {key}" in error.value.detail
    assert error.value.detail.endswith(
        "Refaceţi redactarea capitolului (versiunea nouă a promptului)."
    )
