"""#163 golden acceptance: audit-case-a ch. 2-3 keeps its reference's structure (the audit
base: the case has no previous audit) at the length of her final, written without Ema.

Opt-in: the acceptance run sets EMA_CH23_DRAFT to the draft it rendered. Invented numbers and
client data stay with the draft checks, which fail closed.
"""

import os
from pathlib import Path

import pytest
from tests.golden.cases import case_path
from tests.golden.ch23_baseline import score

pytestmark = pytest.mark.golden


def test_audit_case_a_ch23_keeps_the_reference_structure_at_her_length() -> None:
    draft = os.environ.get("EMA_CH23_DRAFT")
    if not draft:
        pytest.skip("set EMA_CH23_DRAFT to the rendered audit-case-a draft to score ch. 2-3")
    # audit-01 is the configured audit base's source (test_s10b_audit_base).
    baseline = score(Path(draft), case_path("audit-01"), case_path("audit-case-a", "final"))
    assert baseline.passed, baseline.report()
