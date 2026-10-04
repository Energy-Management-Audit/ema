"""Fill v2 on synthetic dossiers: one extraction call, one retry, pre-flight, split, replay."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from tests.unit.audit.test_fill_stage import OPENAI_MODEL, synthetic_dossier, use_provider
from tests.workspace_jobs import create_job

from ema.audit.catalogue import CATALOGUE, Section
from ema.audit.catalogue_labels import field_label
from ema.audit.catalogue_types import MAX_PASSAGES
from ema.audit.fill_extract import (
    OUTPUT_TOKENS,
    PASSAGE_TOKENS,
    PROMPT_TOKENS,
    PROMPT_VERSION,
    THINKING_TOKENS,
    Extraction,
    ExtractSummary,
    extract_facts,
    instructions,
)
from ema.audit.fill_stage import fill_sections
from ema.audit.fill_tools import FillDocument
from ema.cli.install_check import RESOURCE_FILES
from ema.core.errors import EmaError
from ema.core.llm import ReplayProvider
from ema.core.llm.models import selected_model
from ema.core.llm.types import Exchange, ToolSpec
from ema.core.review.fields import fields
from ema.core.workspace import Workspace

PERMIT_PAGES = ("Prima pagină a autorizaţiei.", "Amplasament: zona industrială Vest, lot 4.")
DOCUMENTS = {
    "fisa.txt": FillDocument(
        "fisa.txt", "Firma Exemplu SRL are sediul în Alba. Activitate: vopsire industrială."
    ),
    "permit.pdf": FillDocument("permit.pdf", "", page_texts=PERMIT_PAGES),
}
COMPANY = {
    "key": "audit.company_name",
    "value": "Firma Exemplu SRL",
    "file": "F1",
    "page": 1,
    "quote": "Firma Exemplu SRL are sediul în Alba.",
}
ACTIVITY = {
    "key": "audit.business_activity",
    "value": "vopsire industrială",
    "file": "F1",
    "page": 1,
    "quote": "Activitate: vopsire industrială.",
}
LOCATION = {
    "key": "audit.location",
    "value": "zona industrială Vest",
    "file": "F2",
    "page": 2,
    "quote": "Amplasament: zona industrială Vest, lot 4.",
}

ALLOWANCE = OUTPUT_TOKENS + THINKING_TOKENS


class Scripted:
    """A live-looking provider that plays fixed extractions and keeps what it was sent."""

    name = "openai"

    def __init__(self, answers: list[dict[str, Any]]) -> None:
        self.answers = answers
        self.sent: list[list[dict[str, Any]]] = []
        self.max_output_tokens: list[int] = []

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
        del model, tools, schema, synthetic, prompt_version, attachments
        self.sent.append(json.loads(json.dumps(messages)))
        self.max_output_tokens.append(max_output_tokens)
        answer = self.answers[len(self.sent) - 1]
        return Exchange(json.dumps(answer, ensure_ascii=False), (), 1000, 100)


def sections(*ids: str) -> list[Section]:
    return [item for item in CATALOGUE if item.id in ids]


def job(tmp_path: Path) -> tuple[Workspace, str]:
    ws = Workspace(tmp_path / "workspace")
    return ws, create_job(ws, "audit", "made-up", 2026)


def extract(
    ws: Workspace,
    job: str,
    wanted: list[Section],
    provider: Any,
    documents: dict[str, FillDocument] = DOCUMENTS,
    model_id: str = OPENAI_MODEL,
) -> ExtractSummary:
    return extract_facts(
        ws,
        job,
        wanted,
        documents=documents,
        provider=provider,
        model_id=model_id,
        artifacts=ws.root / "artifacts",
        client_live=True,
    )


def values(ws: Workspace, job: str) -> dict[str, tuple[str, str]]:
    return {item.key: (str(item.value), item.presence) for item in fields(ws, job)}


def log_events(ws: Workspace, job: str, event: str) -> list[dict[str, Any]]:
    with ws.connect() as db:
        lines = (ws.job_path(db, job) / "log.jsonl").read_text(encoding="utf-8").splitlines()
    return [item for item in map(json.loads, lines) if item["event"] == event]


def test_the_output_schema_and_the_instructions_are_the_plan_contract() -> None:
    schema = Extraction.model_json_schema()
    assert list(schema["properties"]) == ["facts", "missing"]
    fact = schema["$defs"]["ExtractedFact"]
    assert list(fact["properties"]) == ["key", "value", "file", "page", "quote"]
    assert fact["required"] == ["key", "value", "file", "page", "quote"]
    assert ("audit", "prompts", "extract_v1.txt") in RESOURCE_FILES
    assert instructions().startswith("Establish the listed facts from the dossier files.")
    assert (PROMPT_TOKENS, OUTPUT_TOKENS, PROMPT_VERSION) == (300_000, 8_000, "audit-extract-v2")


def test_one_call_fills_several_sections(tmp_path: Path) -> None:
    ws, job_id = job(tmp_path)
    provider = Scripted([{"facts": [COMPANY, ACTIVITY, LOCATION], "missing": ["audit.cui"]}])
    wanted = sections("ch2.date_generale", "ch2.activitate", "ch2.localizare")

    summary = extract(ws, job_id, wanted, provider)

    assert len(provider.sent) == 1
    assert summary.calls == 1
    assert summary.facts == ("audit.company_name", "audit.business_activity", "audit.location")
    assert summary.rejected == {}
    found = values(ws, job_id)
    assert found["audit.company_name"] == ("Firma Exemplu SRL", "found")
    # A narrative fact is its passage: the quote, whatever value the model gave.
    assert found["audit.business_activity"] == ("Activitate: vopsire industrială.", "found")
    assert found["audit.location"] == ("zona industrială Vest", "found")
    assert "audit.cui" in summary.missing and found["audit.cui"][1] == "not_found"
    system, user = provider.sent[0]
    assert system == {"role": "system", "content": instructions()}
    content = user["content"]
    assert content.startswith(
        "Fapte de stabilit:\naudit.company_name — Denumirea societăţii — ch2.date_generale\n"
    )
    assert f"audit.location — {field_label('audit.location')} — ch2.localizare" in content
    assert content.endswith(
        "Fişiere:\nF1: fisa.txt\n[F1 p.1]\nFirma Exemplu SRL are sediul în Alba. "
        "Activitate: vopsire industrială.\n\nF2: permit.pdf\n[F2 p.1]\n"
        "Prima pagină a autorizaţiei.\n[F2 p.2]\nAmplasament: zona industrială Vest, lot 4."
    )
    assert provider.max_output_tokens == [ALLOWANCE + MAX_PASSAGES * PASSAGE_TOKENS]
    recording = json.loads((ws.root / "artifacts/extract-1.json").read_text("utf-8"))
    assert (recording["source"], len(recording["responses"])) == ("recorded", 1)
    (estimate,) = log_events(ws, job_id, "ai_estimate")
    assert estimate["tokens"] == (len(system["content"]) + len(content)) // 4
    with ws.connect() as db:
        calls = db.execute("SELECT section, prompt_version FROM llm_calls").fetchall()
    assert [tuple(row) for row in calls] == [("extract", PROMPT_VERSION)]


def test_a_wrong_quote_is_retried_once_with_only_that_item(tmp_path: Path) -> None:
    ws, job_id = job(tmp_path)
    wrong = {**LOCATION, "quote": "Amplasament: zona industrială Est."}
    provider = Scripted(
        [{"facts": [COMPANY, wrong], "missing": []}, {"facts": [LOCATION], "missing": []}]
    )

    summary = extract(ws, job_id, sections("ch2.date_generale", "ch2.localizare"), provider)

    assert summary.calls == len(provider.sent) == 2
    assert summary.rejected == {"audit.location": "evidence_quote"}
    assert values(ws, job_id)["audit.location"] == ("zona industrială Vest", "found")
    retry = provider.sent[1][1]["content"]
    head, items = retry.split("\n\nFapte respinse:\n")
    assert (
        head
        == f"Fapte de stabilit:\naudit.location — {field_label('audit.location')} — ch2.localizare"
    )
    (item,) = json.loads(items)
    assert item == {
        **wrong,
        "reason": "evidence_quote: Fragmentul citat nu apare în fişier. (F2)",
        "page_text": PERMIT_PAGES[1],
    }
    # Never the whole dossier: no other file or page goes with the retry.
    assert "Firma Exemplu" not in retry and PERMIT_PAGES[0] not in retry
    assert (ws.root / "artifacts/extract-2.json").is_file()


def test_a_fact_still_wrong_after_the_retry_is_missing_without_a_third_call(
    tmp_path: Path,
) -> None:
    ws, job_id = job(tmp_path)
    wrong = {**LOCATION, "value": "zona Est"}
    provider = Scripted([{"facts": [wrong], "missing": []}, {"facts": [wrong], "missing": []}])

    summary = extract(ws, job_id, sections("ch2.localizare"), provider)

    assert len(provider.sent) == 2
    assert summary.rejected == {"audit.location": "value_unverified"}
    assert summary.missing == ("audit.location",)
    assert values(ws, job_id)["audit.location"] == ("None", "not_found")


def test_wrong_page_file_and_near_match_are_rejected(tmp_path: Path) -> None:
    for index, (bad, code) in enumerate(
        (
            ({**LOCATION, "page": 1}, "evidence_quote"),
            ({**LOCATION, "file": "F1"}, "page_missing"),
            ({**LOCATION, "quote": LOCATION["quote"].replace("Vest", "Est")}, "evidence_quote"),
        )
    ):
        ws, job_id = job(tmp_path / str(index))
        provider = Scripted([{"facts": [bad], "missing": []}, {"facts": [], "missing": []}])
        summary = extract(ws, job_id, sections("ch2.localizare"), provider)
        assert summary.rejected == {"audit.location": code}
        assert summary.missing == ("audit.location",)


def test_retry_includes_every_rejected_page_for_one_key(tmp_path: Path) -> None:
    ws, job_id = job(tmp_path)
    bad1 = {**LOCATION, "page": 1}
    bad2 = {**LOCATION, "quote": "Amplasament: zona industrială Est."}
    provider = Scripted([{"facts": [bad1, bad2], "missing": []}, {"facts": [], "missing": []}])
    extract(ws, job_id, sections("ch2.localizare"), provider)
    items = json.loads(provider.sent[1][1]["content"].split("\n\nFapte respinse:\n")[1])
    assert [(item["page"], item["quote"]) for item in items] == [
        (1, bad1["quote"]),
        (2, bad2["quote"]),
    ]


def test_single_oversized_file_splits_on_page_markers(tmp_path: Path) -> None:
    ws, job_id = job(tmp_path)
    pages = tuple(f"page-{number} " + "x" * 5900 for number in range(1, 230))
    documents = {"large.pdf": FillDocument("large.pdf", "", page_texts=pages)}
    provider = Scripted([{"facts": [], "missing": []}] * 4)
    summary = extract(ws, job_id, sections("ch2.localizare"), provider, documents)
    assert summary.calls > 1
    sent = ["".join(str(message["content"]) for message in call) for call in provider.sent]
    assert all(len(request) // 4 <= PROMPT_TOKENS for request in sent)
    markers = [int(page) for request in sent for page in re.findall(r"\[F1 p\.(\d+)\]", request)]
    assert markers == list(range(1, 230))
    assert all("F1: large.pdf" in request for request in sent)


def test_header_plus_one_page_over_bound_fails_before_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("ema.audit.fill_extract.PROMPT_TOKENS", 20)
    ws, job_id = job(tmp_path)
    provider = Scripted([])
    with pytest.raises(EmaError) as error:
        extract(ws, job_id, sections("ch2.localizare"), provider)
    assert error.value.code == "ai_prompt_size"
    assert provider.sent == []


def test_schema_retry_reestimates_its_larger_request(tmp_path: Path) -> None:
    ws, job_id = job(tmp_path)
    provider = Scripted([{"facts": "invalid", "missing": []}, {"facts": [], "missing": []}])
    extract(ws, job_id, sections("ch2.localizare"), provider)
    estimates = log_events(ws, job_id, "ai_estimate")
    assert len(estimates) == 2
    assert estimates[1]["tokens"] > estimates[0]["tokens"]
    for estimate, messages in zip(estimates, provider.sent, strict=True):
        assert estimate["tokens"] == sum(len(str(item["content"])) for item in messages) // 4
        assert estimate["usd"] == round(
            selected_model("openai", OPENAI_MODEL).cost(estimate["tokens"], ALLOWANCE), 6
        )


def test_preflight_refuses_over_the_job_budget_before_any_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Nothing is spent yet, so only the estimate can exceed the budget.
    monkeypatch.setenv("EMA_AI_JOB_BUDGET_USD", "0.001")
    ws, job_id = job(tmp_path)
    provider = Scripted([])

    with pytest.raises(EmaError) as refused:
        extract(ws, job_id, sections("ch2.date_generale"), provider)

    assert refused.value.code == "ai_budget"
    assert provider.sent == []
    (estimate,) = log_events(ws, job_id, "ai_estimate")
    model = selected_model("openai", OPENAI_MODEL)
    assert estimate["usd"] == round(model.cost(estimate["tokens"], ALLOWANCE), 6)
    assert estimate["usd"] > 0.001 and estimate["job_usd"] == 0
    assert refused.value.detail == f"0.00 + {estimate['usd']:.2f} USD"


def test_a_dossier_over_the_bound_is_split_and_the_first_verified_fact_wins(
    tmp_path: Path,
) -> None:
    ws, job_id = job(tmp_path)
    filler = "Rând sintetic de completare fără date.\n" * 13_000
    documents = {
        "unu.txt": FillDocument("unu.txt", "Firma Unu SRL.\n" + filler),
        "doi.txt": FillDocument("doi.txt", filler),
        "trei.txt": FillDocument("trei.txt", "Firma Trei SRL, amplasament Vest.\n" + filler),
    }
    first = {**COMPANY, "value": "Firma Unu SRL", "quote": "Firma Unu SRL."}
    later = {**COMPANY, "value": "Firma Trei SRL", "file": "F3", "quote": "Firma Trei SRL,"}
    place = {**LOCATION, "value": "Vest", "file": "F3", "page": 1, "quote": "amplasament Vest."}
    provider = Scripted(
        [{"facts": [first], "missing": []}, {"facts": [later, place], "missing": []}]
    )

    summary = extract(
        ws, job_id, sections("ch2.date_generale", "ch2.localizare"), provider, documents
    )

    assert len(provider.sent) == 2
    for messages in provider.sent:
        assert sum(len(message["content"]) for message in messages) // 4 <= PROMPT_TOKENS
    one, two = (messages[1]["content"] for messages in provider.sent)
    assert "\nF1: unu.txt\n" in one and "\n\nF2: doi.txt\n" in one and "F3:" not in one
    assert "Fişiere:\nF3: trei.txt\n" in two and "F1:" not in two
    assert summary.rejected == {}
    found = values(ws, job_id)
    assert found["audit.company_name"] == ("Firma Unu SRL", "found")
    assert found["audit.location"] == ("Vest", "found")


def test_replay_reproduces_the_recorded_fill_offline(tmp_path: Path) -> None:
    wrong = {**LOCATION, "quote": "Amplasament: zona industrială Est."}
    live = Scripted(
        [{"facts": [COMPANY, wrong], "missing": []}, {"facts": [LOCATION], "missing": []}]
    )
    wanted = sections("ch2.date_generale", "ch2.localizare")
    ws, job_id = job(tmp_path / "live")
    recorded = extract(ws, job_id, wanted, live)
    rows = [
        json.loads((ws.root / f"artifacts/extract-{n}.json").read_text("utf-8")) for n in (1, 2)
    ]
    replay_file = tmp_path / "replay.json"
    replay_file.write_text(
        json.dumps({**rows[0], "responses": [row["responses"][0] for row in rows]}), "utf-8"
    )

    replay = ReplayProvider(replay_file)
    again_ws, again_job = job(tmp_path / "replay")
    replayed = extract(again_ws, again_job, wanted, replay, model_id=replay.model_id)

    assert replay.calls == 2
    assert replayed == recorded
    assert values(again_ws, again_job) == values(ws, job_id)
    assert not (again_ws.root / "artifacts").exists()


def test_the_synthetic_dossier_needs_at_most_two_calls_without_a_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMA_AI_CLIENT_LIVE", "1")
    ws, job_id = synthetic_dossier(tmp_path, monkeypatch)
    supplied = {key for key, (_, presence) in values(ws, job_id).items() if presence == "found"}
    provider = Scripted([{"facts": [COMPANY], "missing": []}])
    use_provider(monkeypatch, provider, OPENAI_MODEL)

    summary = fill_sections(ws, job_id)

    assert len(provider.sent) <= 2
    assert summary.extracted is not None and summary.extracted.rejected == {}
    found = values(ws, job_id)
    assert found["audit.company_name"] == ("Firma Exemplu SRL", "found")
    # A value the Necesar info supplied is never overwritten with missing.
    assert "audit.tep_class" in supplied
    assert found["audit.tep_class"][1] == "found"
    assert not supplied & set(summary.extracted.missing)
