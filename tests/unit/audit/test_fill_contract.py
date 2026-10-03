"""The Fill tool contract a live model can follow, and the bounds on what a section costs."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from tests.unit.audit.test_fill_stage import (
    FIXTURES,
    OPENAI_MODEL,
    SECTION,
    run_events,
    synthetic_dossier,
    use_provider,
)
from tests.workspace_jobs import create_job

from ema.audit.catalogue import CATALOGUE
from ema.audit.draft_schema import SECTION_FACTS
from ema.audit.fill_files import PAGE_CHARS
from ema.audit.fill_stage import FILL_STEPS, fill_section, fill_sections, stopped_warning
from ema.audit.fill_tools import FillDocument, FillTools
from ema.core.errors import EmaError
from ema.core.llm import AgentContext, Limits, ReplayProvider, agent_state, run_agent
from ema.core.llm.agent import Tool, compacted, job_spend
from ema.core.llm.types import Exchange, ToolCall, ToolSpec
from ema.core.review.fields import fields
from ema.core.workspace import Workspace

RECORDING = FIXTURES / "llm/fill_contract_synthetic_openai.json"


def _tools(tmp_path: Path, documents: dict[str, FillDocument] | None = None) -> FillTools:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "made-up", 2026)
    documents = documents or {
        "fisa.txt": FillDocument("fisa.txt", "Firma Exemplu SRL are sediul în Alba."),
        "permit.pdf": FillDocument("permit.pdf", "", page_texts=("Prima pagină.", "Sediu: Alba.")),
    }
    return FillTools(ws, job, SECTION, documents)


class Scripted:
    """A live-looking provider that plays a fixed list of steps and keeps what it was sent."""

    name = "openai"

    def __init__(self, steps: list[Exchange]) -> None:
        self.steps = steps
        self.sent: list[list[dict[str, Any]]] = []
        self.tools: tuple[ToolSpec, ...] = ()

    def respond(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: tuple[ToolSpec, ...],
        schema: dict[str, Any] | None = None,
        max_output_tokens: int = 4096,
        synthetic: bool = False,
        *,
        prompt_version: str = "",
        attachments: Mapping[str, bytes] | None = None,
    ) -> Exchange:
        del model, schema, max_output_tokens, synthetic, prompt_version, attachments
        self.sent.append(json.loads(json.dumps(messages)))
        self.tools = tools
        return (
            self.steps[len(self.sent) - 1]
            if len(self.sent) <= len(self.steps)
            else (Exchange("Gata.", (), 10, 10))
        )


def _step(number: int, name: str, args: dict[str, Any], tokens: int = 10) -> Exchange:
    return Exchange(None, (ToolCall(f"c{number}", name, args),), tokens, 10)


def test_every_fill_argument_is_described_with_the_contract_wording(tmp_path: Path) -> None:
    specs = {name: tool.spec for name, tool in _tools(tmp_path).tools().items()}

    assert set(specs) == {
        "read_file",
        "search_files",
        "read_dataset",
        "record_fact",
        "mark_missing",
        "mark_later",
        "propose_na",
    }
    for spec in specs.values():
        for argument in spec.parameters["properties"].values():
            assert argument["description"]
    record = specs["record_fact"].parameters["properties"]
    assert record["name"]["description"] == (
        "exact dossier file name or its id from the task (e.g. F3)"
    )
    assert record["quote"]["description"] == "verbatim excerpt of that file, 10-400 characters"
    assert record["source_key"]["description"] == (
        "only for a dataset field key from read_dataset; never a file name"
    )
    assert record["value"]["description"] == "the fact's value as stated in the quote"
    assert specs["read_file"].parameters["properties"]["name"] == record["name"]


def test_a_file_is_found_by_id_exact_name_or_name_without_extension(tmp_path: Path) -> None:
    tools = _tools(tmp_path)
    tools.documents["plan.pdf"] = FillDocument("plan.pdf", "A")
    tools.documents["plan.docx"] = FillDocument("plan.docx", "B")

    for name in ("F2", "permit.pdf", "permit"):
        assert tools.read_file({"name": name})["name"] == "permit.pdf"
    with pytest.raises(EmaError) as ambiguous:
        tools.read_file({"name": "plan"})
    assert ambiguous.value.code == "file_missing"
    recorded = tools.record_fact(
        {"key": "audit.address", "value": "Alba", "name": "fisa", "quote": "sediul în Alba."}
    )
    assert recorded["key"] == "audit.address"


def test_read_file_serves_bounded_pages(tmp_path: Path) -> None:
    line = "Rând sintetic de test cu valori inventate.\n"
    text = line * (2 * PAGE_CHARS // len(line) + 5)
    tools = _tools(tmp_path, {"lung.txt": FillDocument("lung.txt", text)})

    first = tools.read_file({"name": "F1"})
    assert first["page_count"] == 3
    pages = [tools.read_file({"name": "F1", "page": page}) for page in (1, 2, 3)]
    assert all(len(page["text"]) <= PAGE_CHARS for page in pages)
    assert "".join(page["text"] for page in pages) == text
    assert pages[0] == first
    with pytest.raises(EmaError) as beyond:
        tools.read_file({"name": "F1", "page": 4})
    assert beyond.value.code == "page_missing"
    pdf = _tools(tmp_path / "pdf").read_file({"name": "permit.pdf", "page": 2})
    assert pdf == {
        "file": "F2",
        "name": "permit.pdf",
        "page": 2,
        "page_count": 2,
        "text": "Sediu: Alba.",
    }


def test_search_files_returns_at_most_eight_passages_with_file_and_page(tmp_path: Path) -> None:
    filler = "x" * 1000
    text = "".join(f"{filler} Suprafaţă {number} m² " for number in range(12))
    tools = _tools(
        tmp_path, {"a.txt": FillDocument("a.txt", "nimic"), "b.txt": FillDocument("b.txt", text)}
    )

    found = tools.search_files({"query": "suprafata"})["passages"]
    assert len(found) == 8
    assert {(item["file"], item["page"]) for item in found} <= {("F2", 1), ("F2", 2), ("F2", 3)}
    assert all(len(item["text"]) <= 2 * 300 + len("Suprafaţă") for item in found)
    assert "Suprafaţă 0 m²" in found[0]["text"]
    words = tools.search_files({"query": "aria suprafaţă clădire"})["passages"]
    assert words and all("Suprafaţă" in item["text"] for item in words)
    assert tools.search_files({"query": "inexistent"}) == {"passages": []}


def test_read_dataset_returns_only_the_sections_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, job = synthetic_dossier(tmp_path, monkeypatch)
    section = next(item for item in CATALOGUE if item.id == SECTION)
    tools = FillTools(ws, job, SECTION, {})

    rows = tools.read_dataset({})
    keys = {row["key"] for row in rows}
    assert keys
    assert keys <= {str(fact) for fact in section.facts}
    assert len(fields(ws, job)) > len(keys)
    outside = next(item.key for item in fields(ws, job) if item.key not in keys)
    assert tools.read_dataset({"key": outside}) == []


def test_replay_of_the_trial_mistakes_gets_reasons_then_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, job = synthetic_dossier(tmp_path, monkeypatch)
    replay = ReplayProvider(RECORDING)
    use_provider(monkeypatch, replay, replay.model_id)

    summary = fill_sections(ws, job, [SECTION])

    assert summary.sections == {SECTION: "done"}
    assert replay.calls == 3
    state = agent_state(ws, job, SECTION)
    assert state is not None
    assert state.messages[1]["content"].endswith("Fişiere:\nF1: fisa.txt\nF2: permit.pdf")
    rejected = [
        message["content"]
        for message in state.messages
        if message["role"] == "tool" and "error" in message["content"]
    ]
    assert [item["error"] for item in rejected] == ["fact_source", "file_missing"]
    assert rejected[1]["reason"] == "Fişierul cerut lipseşte: Date generale."
    for item in rejected:
        assert item["expected"]["name"] == (
            "optional: exact dossier file name or its id from the task (e.g. F3)"
        )
        assert item["expected"]["key"] == "required: a fact key listed in the task"
    found = {item.key: item for item in fields(ws, job)}
    assert found["audit.company_name"].value == "Firma Exemplu SRL"
    assert found["audit.address"].value == "Alba"


def test_history_keeps_the_last_four_tool_results(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "made-up", 2026)
    echo = Tool(ToolSpec("echo", "Echo", {"type": "object", "properties": {}}), lambda _: "r" * 50)
    provider = Scripted([_step(number, "echo", {}) for number in range(6)])
    context = AgentContext(ws, job, SECTION, provider, OPENAI_MODEL, "test", synthetic=True)

    state = run_agent(context, "system", {"echo": echo}, Limits(8), task="task")

    assert state.status == "done"
    last = provider.sent[-1]
    results = [message["content"] for message in last if message["role"] == "tool"]
    assert results == ["[rezultat omis: echo, 50 caractere]"] * 2 + ["r" * 50] * 4
    assert [m["content"] for m in state.messages if m["role"] == "tool"] == ["r" * 50] * 6
    assert compacted(state.messages) == last


def test_job_budget_stops_the_fill_stage_and_logs_the_spend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMA_AI_CLIENT_LIVE", "1")
    monkeypatch.setenv("EMA_AI_JOB_BUDGET_USD", "0.0001")
    ws, job = synthetic_dossier(tmp_path, monkeypatch)
    # One answer over the budget: the next section must not start a call.
    provider = Scripted([Exchange("Gata.", (), 1_000_000, 10)])
    use_provider(monkeypatch, provider, OPENAI_MODEL)

    first, second, *rest = [item.id for item in CATALOGUE if item.id in SECTION_FACTS][:4]
    summary = fill_sections(ws, job, [first, second, *rest])

    spent = job_spend(ws, job)
    assert spent > 0.0001
    assert summary.sections == {first: "done"}
    assert summary.failed == {second: "ai_budget"}
    assert summary.stopped == tuple(rest)
    assert len(provider.sent) == 1
    with pytest.raises(EmaError) as stopped:
        fill_section(
            ws,
            job,
            next(item for item in CATALOGUE if item.id == rest[0]),
            {},
            provider=provider,
            model_id=OPENAI_MODEL,
            limits=Limits(FILL_STEPS),
            client_live=True,
        )
    assert (stopped.value.code, stopped.value.user_message_ro, stopped.value.detail) == (
        "ai_budget",
        "Bugetul AI al lucrării s-a epuizat.",
        f"{spent:.2f} USD",
    )
    kind, payload = run_events(ws, summary.run)[-1]
    assert (kind, payload["warnings"]) == ("stage_finished", 1)
    assert stopped_warning(summary.failed, summary.stopped) == [
        f"Bugetul AI al lucrării s-a epuizat: {len(rest)} secţiuni rămase."
    ]
    with ws.connect() as db:
        log = (ws.job_path(db, job) / "log.jsonl").read_text(encoding="utf-8")
    spend = [json.loads(line) for line in log.splitlines() if '"ai_spend"' in line]
    assert [(item["stage"], item["usd"]) for item in spend] == [("fill", round(spent, 6))]


def test_one_sections_largest_prompt_stays_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, job = synthetic_dossier(tmp_path, monkeypatch)
    line = "Suprafaţa construită a halei sintetice este de 500 m² conform planului.\n"
    documents = {
        "raport.txt": FillDocument("raport.txt", line * 400),
        "fisa.txt": FillDocument("fisa.txt", "Firma Exemplu SRL are sediul în Alba."),
    }
    steps = [
        _step(0, "read_dataset", {}),
        *(_step(page, "read_file", {"name": "F1", "page": page}) for page in range(1, 5)),
        _step(5, "search_files", {"query": "suprafaţa"}),
        *(_step(page, "read_file", {"name": "raport", "page": page}) for page in range(1, 5)),
        _step(10, "read_file", {"name": "F2"}),
    ]
    provider = Scripted(steps)
    section = next(item for item in CATALOGUE if item.id == SECTION)

    state = fill_section(
        ws,
        job,
        section,
        documents,
        provider=provider,
        model_id=OPENAI_MODEL,
        limits=Limits(FILL_STEPS),
        client_live=True,
    )

    assert state.steps == FILL_STEPS
    tools = json.dumps([vars(tool) for tool in provider.tools], ensure_ascii=False)
    largest = max(len(json.dumps(sent, ensure_ascii=False)) for sent in provider.sent)
    assert largest + len(tools) < 40_000
