"""The Fill tool contract that verifies facts, and the job budget shared by AI calls."""

from __future__ import annotations

import json
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from typing import Any

import pytest
from tests.unit.audit.test_fill_stage import OPENAI_MODEL, SECTION, synthetic_dossier
from tests.workspace_jobs import create_job

from ema.audit.catalogue import CATALOGUE
from ema.audit.fill_files import PAGE_CHARS
from ema.audit.fill_tools import FillDocument, FillTools
from ema.core.errors import EmaError
from ema.core.llm import AgentContext, Limits, run_agent
from ema.core.llm.agent import Tool, compacted, job_spend
from ema.core.llm.models import selected_model
from ema.core.llm.types import Exchange, ToolCall, ToolSpec
from ema.core.review.fields import fields
from ema.core.workspace import Workspace


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


def test_colliding_filename_returns_structured_tool_errors(tmp_path: Path) -> None:
    tools = _tools(
        tmp_path,
        {
            "first.txt": FillDocument("first.txt", "First synthetic text."),
            "F1": FillDocument("F1", "Sediu: Alba."),
        },
    )
    provider = Scripted(
        [
            _step(1, "read_file", {"name": "F1"}),
            _step(
                2,
                "record_fact",
                {"key": "audit.address", "value": "Alba", "name": "F1", "quote": "Sediu: Alba."},
            ),
        ]
    )
    context = AgentContext(
        tools.ws, tools.job, SECTION, provider, OPENAI_MODEL, "test", synthetic=True
    )
    state = run_agent(context, "system", tools.tools(), Limits(3))
    rejected = [message["content"] for message in state.messages if message["role"] == "tool"]
    assert [item["error"] for item in rejected] == ["file_ambiguous", "file_ambiguous"]
    assert all("numele complet" in item["reason"] and item["expected"] for item in rejected)
    assert tools.read_file({"name": "first.txt"})["name"] == "first.txt"


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


def test_concurrent_job_calls_allow_only_one_exchange_at_the_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "made-up", 2026)
    exchange = Exchange("Gata.", (), 1_000_000, 0)
    monkeypatch.setenv(
        "EMA_AI_JOB_BUDGET_USD", str(selected_model("openai", OPENAI_MODEL).cost(1_000_000, 0))
    )
    entered, release, second_started = Event(), Event(), Event()

    class Blocking(Scripted):
        def respond(self, *args: Any, **kwargs: Any) -> Exchange:
            entered.set()
            assert release.wait(5)
            return super().respond(*args, **kwargs)

    provider = Blocking([exchange])
    first = AgentContext(ws, job, "first", provider, OPENAI_MODEL, "test", synthetic=True)
    second = AgentContext(ws, job, "second", provider, OPENAI_MODEL, "test", synthetic=True)

    def later() -> str:
        second_started.set()
        try:
            return run_agent(second, "system", {}, Limits(1)).status
        except EmaError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_result = pool.submit(run_agent, first, "system", {}, Limits(1))
        assert entered.wait(5)
        second_result = pool.submit(later)
        assert second_started.wait(5)
        release.set()
        assert first_result.result().status == "done"
        assert second_result.result() == "ai_budget"
    assert len(provider.sent) == 1
    assert job_spend(ws, job) == selected_model("openai", OPENAI_MODEL).cost(1_000_000, 0)
