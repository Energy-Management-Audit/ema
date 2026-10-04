"""The render reads a draft with every fact it cites and the sentence each flag marks."""

from __future__ import annotations

from tests.unit.audit.test_draft_checks import _fact  # pyright: ignore[reportPrivateUsage]

from ema.audit.draft_render import draft_blocks
from ema.audit.draft_schema import DraftText, SectionDraft
from ema.audit.render_writers import review_flags, section_facts
from ema.core.office.blocks import Paragraph


def test_numbered_passages_of_the_section_facts_reach_the_render() -> None:
    by_key = {
        key: _fact(key, "Pasaj.")
        for key in (
            "audit.process_sections",
            "audit.process_sections.2",
            "audit.history.2",
            "audit.company_name",
        )
    }

    assert set(section_facts("ch3.process", by_key)) == {
        "audit.process_sections",
        "audit.process_sections.2",
    }


def test_a_stored_support_flag_keeps_its_sentence() -> None:
    stored: list[dict[str, str | None]] = [
        {
            "code": "unsupported",
            "location": "paragraph:0",
            "detail": "nesusţinut",
            "sentence": "A.",
        },
        {"code": "uncited_sentence", "location": "paragraph:1", "detail": "B."},
    ]

    flags = review_flags(stored)

    assert [(flag.code, flag.sentence) for flag in flags] == [
        ("unsupported", "A."),
        ("uncited_sentence", None),
    ]


def test_internal_codes_read_as_words_in_the_prose() -> None:
    employees = _fact("audit.employees", 379, "number").model_copy(
        update={"unit": "persons", "decimals": 0}
    )
    tep_class = _fact("audit.tep_class", "below_1000_tep")
    draft = SectionDraft(
        section="ch2.date_generale",
        status="drafted",
        paragraphs=[
            DraftText(
                text="Are {{f:audit.employees}} angajaţi, în clasa {{f:audit.tep_class}}.",
                fact_ids=["audit.employees", "audit.tep_class"],
            )
        ],
    )

    (block, *_) = draft_blocks(
        draft, {"audit.employees": employees, "audit.tep_class": tep_class}, ()
    )

    assert isinstance(block, Paragraph)
    assert block.segments == ["Are 379 angajaţi, în clasa sub 1.000 tep."]
