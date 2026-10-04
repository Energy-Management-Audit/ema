"""Fill v2 narrative facts: whole verbatim passages, several per fact, an honest allowance."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.unit.audit.test_fill_extract import (
    OPENAI_MODEL,
    Scripted,
    extract,
    job,
    log_events,
    sections,
    values,
)

from ema.audit.catalogue_labels import field_label
from ema.audit.catalogue_types import MAX_PASSAGES, PASSAGE_FACTS
from ema.audit.fill_extract import (
    OUTPUT_TOKENS,
    PASSAGE_CHARS,
    PASSAGE_TOKENS,
    instructions,
    output_tokens,
)
from ema.audit.fill_tools import FillDocument
from ema.core.llm import ReplayProvider
from ema.core.llm.models import selected_model
from ema.core.review.fields import fields

# A synthetic process-flow dossier: each page describes one stage in several paragraphs.
STAGES = tuple(
    f"Etapa {number}. Piesele sosesc pe conveiorul liniei {number}, unde sunt degresate "
    "într-o baie alcalină încălzită şi clătite cu apă demineralizată.\n"
    + "Uscarea se face într-un cuptor cu aer cald, alimentat cu gaz natural, după care piesele "
    "trec în cabina de vopsire în câmp electrostatic şi apoi în cuptorul de polimerizare.\n" * 6
    for number in range(1, 9)
)
FLOW = {"flux.pdf": FillDocument("flux.pdf", "", page_texts=STAGES)}


def passage(page: int, **changes: Any) -> dict[str, Any]:
    return {
        "key": "audit.process_sections",
        "value": "",
        "file": "F1",
        "page": page,
        "quote": STAGES[page - 1].strip(),
    } | changes


def test_the_prompt_states_the_passage_rule_with_the_code_limits() -> None:
    text = instructions()
    assert 'A fact whose line ends with "— pasaj" is a description' in text
    assert f"up to {PASSAGE_CHARS} characters" in text
    assert f"up to {MAX_PASSAGES} for one key" in text
    assert {str(key) for key in PASSAGE_FACTS} == {
        "audit.history",
        "audit.business_activity",
        "audit.process_sections",
        "audit.water_supply",
        "audit.electricity_supply",
        "audit.gas_supply",
        "audit.compressed_air",
        "audit.hvac",
        "audit.lighting",
    }


def test_a_long_passage_verifies_whole_and_page_exact(tmp_path: Path) -> None:
    ws, job_id = job(tmp_path)
    assert len(STAGES[0]) > 1000
    provider = Scripted([{"facts": [passage(1)], "missing": []}])

    summary = extract(ws, job_id, sections("ch3.process"), provider, FLOW)

    assert summary.facts == ("audit.process_sections",) and summary.rejected == {}
    content = provider.sent[0][1]["content"]
    line = f"audit.process_sections — {field_label('audit.process_sections')} — ch3.process"
    assert f"{line} — pasaj\n" in content
    (equipment,) = [item for item in content.splitlines() if item.startswith("audit.equipment")]
    assert equipment == f"audit.equipment — {field_label('audit.equipment')} — ch3.process"
    (stored,) = [item for item in fields(ws, job_id) if item.key == "audit.process_sections"]
    assert stored.value == STAGES[0].strip()
    with ws.connect() as db:
        (row,) = db.execute("SELECT data FROM evidence WHERE id=?", stored.evidence).fetchall()
    evidence = json.loads(row["data"])
    assert evidence["quote"] == STAGES[0].strip()
    assert evidence["locator"]["page"] == 1


def test_each_distinct_passage_is_its_own_numbered_fact(tmp_path: Path) -> None:
    ws, job_id = job(tmp_path)
    returned = [passage(page) for page in (1, 2, 1, 3, 4, 5, 6, 7, 8)]
    provider = Scripted([{"facts": returned, "missing": []}])

    extract(ws, job_id, sections("ch3.process"), provider, FLOW)

    found = values(ws, job_id)
    numbered = ["audit.process_sections"] + [
        f"audit.process_sections.{number}" for number in range(2, MAX_PASSAGES + 1)
    ]
    # The repeated page 1 is skipped; pages past MAX_PASSAGES are not kept.
    assert [found[key][0] for key in numbered] == [STAGES[page - 1].strip() for page in range(1, 7)]
    assert "audit.process_sections.7" not in found
    assert field_label("audit.process_sections.3") == f"{field_label('audit.process_sections')} (3)"


def test_a_rejected_passage_is_retried_when_another_one_verified(tmp_path: Path) -> None:
    ws, job_id = job(tmp_path)
    slipped = passage(2, quote=STAGES[1].strip().replace("demineralizată", "demineralizata"))
    provider = Scripted(
        [{"facts": [passage(1), slipped], "missing": []}, {"facts": [passage(2)], "missing": []}]
    )

    summary = extract(ws, job_id, sections("ch3.process"), provider, FLOW)

    assert len(provider.sent) == 2
    assert summary.rejected == {"audit.process_sections": "evidence_quote"}
    found = values(ws, job_id)
    assert found["audit.process_sections.2"] == (STAGES[1].strip(), "found")
    retry = provider.sent[1][1]["content"]
    assert retry.startswith("Fapte de stabilit:\naudit.process_sections — ")
    assert provider.max_output_tokens == [
        OUTPUT_TOKENS + MAX_PASSAGES * PASSAGE_TOKENS,
        OUTPUT_TOKENS + MAX_PASSAGES * PASSAGE_TOKENS,
    ]


def test_the_allowance_and_preflight_price_every_passage(tmp_path: Path) -> None:
    wanted = sections("ch2.istorie", "ch2.activitate", "ch2.localizare")
    facts = [(str(fact), item.id) for item in wanted for fact in item.facts]
    assert output_tokens(facts) == OUTPUT_TOKENS + 2 * MAX_PASSAGES * PASSAGE_TOKENS
    ws, job_id = job(tmp_path)
    provider = Scripted([{"facts": [], "missing": []}])

    extract(ws, job_id, wanted, provider, FLOW)

    assert provider.max_output_tokens == [output_tokens(facts)]
    (estimate,) = log_events(ws, job_id, "ai_estimate")
    model = selected_model("openai", OPENAI_MODEL)
    assert estimate["usd"] == round(model.cost(estimate["tokens"], output_tokens(facts)), 6)


def test_a_rerun_with_fewer_passages_drops_the_stale_ones(tmp_path: Path) -> None:
    ws, job_id = job(tmp_path)
    first = Scripted([{"facts": [passage(page) for page in (1, 2, 3)], "missing": []}])
    extract(ws, job_id, sections("ch3.process"), first, FLOW)
    again = Scripted([{"facts": [passage(4)], "missing": []}])

    extract(ws, job_id, sections("ch3.process"), again, FLOW)

    found = values(ws, job_id)
    assert found["audit.process_sections"] == (STAGES[3].strip(), "found")
    assert found["audit.process_sections.2"][1] == "not_found"
    assert found["audit.process_sections.3"][1] == "not_found"


def test_replay_reproduces_the_recorded_passages_offline(tmp_path: Path) -> None:
    live = Scripted([{"facts": [passage(1), passage(2)], "missing": []}])
    ws, job_id = job(tmp_path / "live")
    recorded = extract(ws, job_id, sections("ch3.process"), live, FLOW)
    replay_file = ws.root / "artifacts/extract-1.json"

    replay = ReplayProvider(replay_file)
    again_ws, again_job = job(tmp_path / "replay")
    replayed = extract(
        again_ws, again_job, sections("ch3.process"), replay, FLOW, model_id=replay.model_id
    )

    assert replay.calls == 1
    assert replayed == recorded
    assert values(again_ws, again_job) == values(ws, job_id)
    assert values(ws, job_id)["audit.process_sections.2"] == (STAGES[1].strip(), "found")
