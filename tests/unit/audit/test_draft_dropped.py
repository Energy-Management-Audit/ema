"""An unsupported sentence of either kind leaves the render and stays in the review (#143 D4)."""

import json
from pathlib import Path

import pytest
from tests.unit.audit.test_draft_structured import SECTION, SupportProvider, _run
from tests.unit.audit.test_section_body import (  # pyright: ignore[reportPrivateUsage]
    FACTS,
    _base,
    _section,
)

from ema.audit.base_anchor import MARKER
from ema.audit.draft_checks import check_draft
from ema.audit.draft_render import render_section, review_payload
from ema.audit.draft_schema import DraftText, SectionDraft

KEPT = "Societatea {{f:audit.company_name}} produce ambalaje."
SUPPLIER = "Energia electrică este furnizată de Elnor."
REASON = "Names a supplier no fact states."


def _verdicts(kind: str) -> str:
    return json.dumps(
        {
            "verdicts": [
                {
                    "location": f"{SECTION}:paragraph:0",
                    "sentence_index": index,
                    "kind": "client" if index == 0 else kind,
                    "supported": index == 0,
                    "reason": "" if index == 0 else REASON,
                }
                for index in (0, 1)
            ]
        }
    )


DRAFT = SectionDraft(
    section=SECTION,
    status="drafted",
    paragraphs=[DraftText(text=f"{KEPT} {SUPPLIER}", fact_ids=["audit.company_name"])],
)


def test_a_supplier_no_fact_names_passes_the_checks_and_the_support_pass_flags_it(
    tmp_path: Path,
) -> None:
    # A single capitalised word no fact holds passes the name check; the support pass decides.
    assert check_draft(DRAFT, FACTS, "synthetic").fatal == ()
    _, _, accepted, flags = _run(tmp_path, [DRAFT], SupportProvider(_verdicts("general")))
    assert accepted == DRAFT
    assert [(flag.code, flag.location, flag.detail, flag.sentence) for flag in flags] == [
        ("unsupported", "paragraph:0", REASON, SUPPLIER)
    ]


@pytest.mark.parametrize("kind", ["client", "general"])
def test_an_unsupported_sentence_is_dropped_without_a_marker_and_listed(
    tmp_path: Path, kind: str
) -> None:
    _, _, _, flags = _run(tmp_path / "run", [DRAFT], SupportProvider(_verdicts(kind)))
    output = tmp_path / "out.docx"
    check = render_section(
        _base(tmp_path / "base.docx"), output, DRAFT, FACTS, flags, job="synthetic"
    )
    written = _section(output)
    assert written[0] == "Societatea Atelier Exemplu produce ambalaje."
    assert not any(MARKER in text or "Elnor" in text for text in written[:-1])
    review = review_payload(DRAFT, check, flags)["review"]
    assert review == [
        {"code": "unsupported", "location": "paragraph:0", "detail": REASON, "sentence": SUPPLIER}
    ]
