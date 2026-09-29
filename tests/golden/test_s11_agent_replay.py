"""Synthetic intake agent replay against both recorded provider formats."""

from pathlib import Path

import pytest
from tests.workspace_jobs import create_job

from ema.audit.intake_tools import IntakeDocument, IntakeTools
from ema.core.llm import AgentContext, Limits, ReplayProvider, run_agent
from ema.core.workspace import Workspace

pytestmark = pytest.mark.golden
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/llm"


@pytest.mark.parametrize("provider", ["openai", "gemini"])
def test_synthetic_agent_replay(provider: str, tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    replay = ReplayProvider(FIXTURES / f"intake_{provider}.json")
    documents = {
        "permit.txt": IntakeDocument("permit.txt", "Permit granted for the workshop"),
        "flow.txt": IntakeDocument("flow.txt", "Flow scheme for paint line"),
        "meter.txt": IntakeDocument("meter.txt", "Meter export for July"),
        "photo.txt": IntakeDocument("photo.txt", "Photo of boiler room"),
    }
    tools = IntakeTools(documents, {number: f"Item {number}" for number in range(1, 14)})
    context = AgentContext(ws, job, "intake", replay, "gemini-3.6-flash", "intake-v1")
    state = run_agent(context, "Classify each file", tools.tools(), Limits(20))
    assert state.status == "done"
    assert replay.calls == 12
    assert tools.classifications == {
        "permit.txt": 2,
        "flow.txt": 5,
        "meter.txt": 13,
        "photo.txt": 4,
    }
    assert tools.missing == {6}
