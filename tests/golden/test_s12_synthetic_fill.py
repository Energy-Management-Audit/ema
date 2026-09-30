"""Request-bound Fill replay over a made-up dossier; no provider call."""

from pathlib import Path
from uuid import UUID

import pytest
from tests.workspace_jobs import create_job

from ema.audit.fill_agent import INSTRUCTIONS, PROMPT_VERSION
from ema.audit.fill_tools import FillDocument, FillTools
from ema.audit.read import read_dossier
from ema.audit.sections import record_applicability
from ema.core.llm import AgentContext, Limits, ReplayProvider, run_agent
from ema.core.llm.agent import AgentState
from ema.core.review.fields import fields
from ema.core.workspace import Workspace

pytestmark = pytest.mark.golden
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def fill_section_replay(
    ws: Workspace,
    job: str,
    section: str,
    documents: dict[str, FillDocument],
    replay: ReplayProvider,
    limits: Limits,
    *,
    model_id: str | None = None,
) -> tuple[AgentState, FillTools]:
    """Run only on a synthetic dossier; S11 persists the resumable transcript."""
    record_applicability(ws, job, section)
    tools = FillTools(ws, job, section, documents)
    context = AgentContext(
        ws, job, section, replay, model_id or replay.model_id, PROMPT_VERSION, synthetic=True
    )
    return run_agent(context, INSTRUCTIONS, tools.tools(), limits), tools


def test_synthetic_fill_rejects_fabrication_and_resumes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path / "workspace")
    # The request-bound recording includes job-owned evidence IDs.
    with monkeypatch.context() as fixed_job:
        fixed_job.setattr("ema.core.jobs.uuid.uuid4", lambda: UUID(int=19))
        job = create_job(ws, "audit", "made-up", 2026)
    read = read_dossier(ws, job, FIXTURES / "audit/synthetic_necesar.xlsx")
    assert any(item.key == "audit.tep_class" for item in read.fields)
    docs = {
        "fisa.txt": FillDocument(
            "fisa.txt", "Firma Exemplu SRL are sediul în Alba. Activitate: vopsire industrială."
        ),
        "permit.pdf": FillDocument(
            "permit.pdf",
            "Autorizație pentru Firma Exemplu SRL. Suprafață autorizată: 500 m².",
        ),
    }
    replay = ReplayProvider(FIXTURES / "llm/fill_synthetic_openai.json")
    state, _ = fill_section_replay(ws, job, "ch2.date_generale", docs, replay, Limits(1))
    assert state.status == "step_limit"
    state, _ = fill_section_replay(ws, job, "ch2.date_generale", docs, replay, Limits(4))
    assert state.status == "done"
    assert replay.calls == 3
    found = {item.key: item for item in fields(ws, job)}
    assert found["audit.company_name"].value == "Firma Exemplu SRL"
    assert "audit.business_activity" not in found
    assert "audit.energy_manager" not in found
    assert "audit.employees" not in found
    errors = [
        message["content"]["error"]
        for message in state.messages
        if message["role"] == "tool"
        and isinstance(message["content"], dict)
        and "error" in message["content"]
    ]
    assert errors == ["evidence_quote", "value_unverified"]


def test_fill_optional_spend_cap_stops_before_provider(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "made-up", 2026)
    replay = ReplayProvider(FIXTURES / "llm/fill_synthetic_openai.json")
    state, _ = fill_section_replay(
        ws, job, "ch2.date_generale", {}, replay, Limits(5, spend_cap_usd=0.000000001)
    )
    assert state.status == "spend_cap"
    assert replay.calls == 0
