"""Chapter five equipment notes: one checked call per measurements run, stored for review."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from tests.workspace_jobs import create_job

from ema.audit.chapter_five import chapter_five_plan, run_measurements
from ema.audit.chapter_five_notes import PROMPT_VERSION, note_issues
from ema.audit.visit import run_visit
from ema.core.jobs import status
from ema.core.llm.models import default_model
from ema.core.llm.types import Exchange, ToolSpec
from ema.core.review import decide, fields, propose
from ema.core.review.evidence import get_evidence
from ema.core.review.models import Evidence, FieldSpec, Manual
from ema.core.workspace import Workspace

PANEL = (
    "Tabloul general de distribuție preia energia electrică de la postul de transformare și o "
    "repartizează către tablourile secundare ale halei de producție; măsurătorile efectuate la "
    "acest nivel caracterizează consumul întregului contur alimentat."
)
BOILER = (
    "Centrala termică produce agentul termic pentru încălzirea spațiilor; termograma permite "
    "identificarea pierderilor de căldură prin carcasă și racorduri, care reduc randamentul "
    "instalației."
)


class FakeNotes:
    """Stands in for the OpenAI adapter: a note per requested item unless `texts` says otherwise;
    `extra` notes are appended to every answer."""

    name = "openai"

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.versions: list[str] = []
        self.thinking: list[int | None] = []
        self.texts: dict[str, str] = {}
        self.extra: list[dict[str, str]] = []

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
        thinking_tokens: int | None = None,
    ) -> Exchange:
        request = json.loads(str(messages[1]["content"]))
        self.requests.append(request)
        self.versions.append(prompt_version)
        self.thinking.append(thinking_tokens)
        notes = [
            {"id": item["id"], "text": self.texts.get(item["id"], PANEL)}
            for item in request["items"]
        ]
        return Exchange(json.dumps({"notes": [*notes, *self.extra]}), (), 1, 1)


@pytest.fixture
def live(monkeypatch: pytest.MonkeyPatch) -> FakeNotes:
    fake = FakeNotes()
    monkeypatch.setenv("EMA_PROVIDER", "openai")
    monkeypatch.setenv("EMA_AI_CLIENT_LIVE", "1")
    monkeypatch.setenv("EMA_LLM_LIVE", "1")
    monkeypatch.setenv("EMA_OPENAI_API_KEY", "synthetic-key")
    monkeypatch.setattr("ema.audit.fill_stage.OpenAIProvider", lambda *_a, **_k: fake)
    return fake


def _accepted(ws: Workspace, job: str, key: str, value: str) -> None:
    field = propose(
        ws, job, FieldSpec(key=key, label=key, value_type="text"), value, [], state="extracted"
    )
    decide(ws, job, field.id, "accept", field.revision, "user")


def _activity(ws: Workspace, job: str) -> None:
    evidence = Evidence(
        id=f"synthetic:activity:{job}",
        provenance="manual",
        locator=Manual(who="synthetic"),
        method="manual",
        retrieved_at=datetime.now(UTC),
        highlight="exact",
    )
    propose(ws, job, "audit.business_activity", "Producția de piese.", [evidence], state="supplied")


def _job(tmp_path: Path, ws: Workspace | None = None) -> tuple[Workspace, str, list[str]]:
    """Two panels, the first with a confirmed analyser, and two thermal images with components."""
    ws = ws or Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    shas: list[str] = []
    for index, slot in enumerate(
        (
            "visit/meter/TG 1/a.png",
            "visit/meter/TS 2/b.png",
            "visit/thermal/c.png",
            "visit/thermal/d.png",
        )
    ):
        image = tmp_path / f"{index}.png"
        Image.new("RGB", (12, 8), (index, 0, 0)).save(image)
        shas.append(ws.add_file("synthetic", image))
        ws.set_slot(job, slot, shas[-1])
    run_visit(ws, job)
    _accepted(ws, job, "meter.tg-1.device", "Analizor Exemplu")
    _accepted(ws, job, f"thermal.{shas[2][:8]}.component", "centrala termică")
    _accepted(ws, job, f"thermal.{shas[3][:8]}.component", "compresorul")
    return ws, job, [f"thermal:{shas[2][:8]}", f"thermal:{shas[3][:8]}"]


def _notes(ws: Workspace, job: str) -> dict[str, str]:
    return {
        field.key.removeprefix("narrative.ch5.equipment."): str(field.value)
        for field in fields(ws, job)
        if field.key.startswith("narrative.ch5.equipment.")
    }


def test_one_call_maps_notes_back_and_records_it(tmp_path: Path, live: FakeNotes) -> None:
    ws, job, thermal = _job(tmp_path)
    _activity(ws, job)
    live.texts[thermal[0]] = BOILER
    result = run_measurements(ws, job)

    assert len(live.requests) == 1
    assert live.versions == [PROMPT_VERSION] == ["audit-ch5-equipment-v1"]
    assert live.thinking[0] is not None
    assert live.requests[0] == {
        "items": [
            {"id": "tg-1", "label": "TG 1", "device": "Analizor Exemplu"},
            {"id": "ts-2", "label": "TS 2"},
            {"id": thermal[0], "component": "centrala termică"},
            {"id": thermal[1], "component": "compresorul"},
        ],
        "activity": ["Producția de piese."],
    }
    assert _notes(ws, job) == {"tg-1": PANEL, "ts-2": PANEL, thermal[0]: BOILER, thermal[1]: PANEL}
    note = next(field for field in fields(ws, job) if field.key == "narrative.ch5.equipment.tg-1")
    assert (note.state, note.review, note.label) == (
        "enriched",
        "pending",
        "Importanța echipamentului – TG 1",
    )
    proof = get_evidence(ws, note.evidence[0])
    assert proof.provenance == "manual"
    assert isinstance(proof.locator, Manual) and proof.locator.who == "agent"
    assert PROMPT_VERSION in (proof.locator.note or "")
    recording = result.plan_path.parent.parent / "ch5-equipment.json"
    assert len(json.loads(recording.read_text(encoding="utf-8"))["responses"]) == 1
    with ws.connect() as db:
        calls = db.execute(
            "SELECT COUNT(*) FROM llm_calls WHERE job_id=? AND section='ch5:equipment'", (job,)
        ).fetchone()[0]
    assert calls == 1
    plan = chapter_five_plan(ws, job)
    assert plan.narratives["narrative.ch5.equipment.tg-1"] == PANEL
    rejected = next(
        field for field in fields(ws, job) if field.key == "narrative.ch5.equipment.ts-2"
    )
    decide(ws, job, rejected.id, "reject", rejected.revision, "user")
    assert chapter_five_plan(ws, job).narratives["narrative.ch5.equipment.ts-2"] is None

    # Replayed for an identical job, the recording gives the same notes without a live call.
    other_ws, other, _ = _job(tmp_path, ws)
    _activity(ws, other)
    run_measurements(other_ws, other, recording=recording)
    assert len(live.requests) == 1
    assert _notes(ws, other) == _notes(ws, job)


def test_dropped_notes_and_reruns_ask_only_for_items_without_one(
    tmp_path: Path, live: FakeNotes
) -> None:
    ws, job, thermal = _job(tmp_path)
    live.texts["ts-2"] = "Tabloul alimentează trei linii."
    live.extra = [{"id": "unknown", "text": PANEL}, {"id": "tg-1", "text": BOILER}]
    run_measurements(ws, job)
    assert _notes(ws, job) == {"tg-1": PANEL, thermal[0]: PANEL, thermal[1]: PANEL}

    live.texts.clear()
    live.extra = []
    run_measurements(ws, job)
    assert [[item["id"] for item in request["items"]] for request in live.requests] == [
        ["tg-1", "ts-2", *thermal],
        ["ts-2"],
    ]
    assert _notes(ws, job)["ts-2"] == PANEL
    run_measurements(ws, job)
    assert len(live.requests) == 2
    assert not any(field.confidence == "conflict" for field in fields(ws, job))


def test_ai_off_or_no_recording_means_no_call_and_no_notes(
    tmp_path: Path, live: FakeNotes, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, job, _ = _job(tmp_path)
    monkeypatch.setenv("EMA_AI_CLIENT_LIVE", "0")
    result = run_measurements(ws, job)
    assert live.requests == []
    assert _notes(ws, job) == {}
    assert not any(
        key.startswith("narrative.ch5.equipment.") for key in chapter_five_plan(ws, job).narratives
    )

    empty = tmp_path / "empty.json"
    empty.write_text(
        json.dumps(
            {
                "source": "recorded",
                "format": "openai-chat-completions",
                "model": default_model("openai").id,
                "responses": [],
            }
        ),
        encoding="utf-8",
    )
    run_measurements(ws, job, recording=empty)
    assert _notes(ws, job) == {}
    assert result.missing_narratives == run_measurements(ws, job).missing_narratives


def test_exhausted_budget_leaves_no_notes_and_a_warning(
    tmp_path: Path, live: FakeNotes, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, job, _ = _job(tmp_path)
    monkeypatch.setenv("EMA_AI_JOB_BUDGET_USD", "0")
    result = run_measurements(ws, job)
    assert live.requests == []
    assert _notes(ws, job) == {}
    with ws.connect() as db:
        log = (ws.job_path(db, job) / "log.jsonl").read_text(encoding="utf-8")
    failed = [json.loads(line) for line in log.splitlines() if "ch5_notes_failed" in line]
    assert [event["code"] for event in failed] == ["ai_budget"]
    run = next(item for item in status(ws, job).runs if item["id"] == result.run)
    assert run["state"] == "ready"


@pytest.mark.parametrize(
    ("text", "issues"),
    [
        (PANEL, []),
        ("Tabloul general TG 1 alimentează hala, conform cerințelor ANRE.", []),
        # A capitalised word after the opening one makes it a name candidate (fix round 1).
        ("Tabloul TG 1 alimentează hala.", ["literal_name"]),
        ("Textul a fost generat automat pentru acest tablou.", ["ai_wording"]),
        ("Tabloul alimentează hala. Este important. Măsurătorile îl descriu.", ["length"]),
        (" ".join(["cuvânt"] * 46) + ".", ["length"]),
        ("Tabloul alimentează 3 linii.", ["literal_number"]),
        ("Tabloul alimentează trei linii.", ["literal_number"]),
        ("Tabloul are un analizor Exemplu montat.", []),
        ("Tabloul alimentează hala din Cluj.", ["literal_name"]),
        ("Tabloul alimentează hala firmei Acme.", []),
        ("Compresorul asigură aerul comprimat.", []),
        ("Atlas Copco asigură aerul comprimat.", ["literal_name"]),
        ("Tabloul alimentează hala. Atlas Copco asigură aerul.", ["literal_name"]),
        ("ABB livrează tabloul.", ["literal_name"]),
        ("TG1 alimentează hala.", ["literal_name"]),
        ("Analizor Exemplu măsoară tabloul.", []),
    ],
)
def test_note_checks(text: str, issues: list[str]) -> None:
    assert (
        note_issues(text, ("TG 1", "Analizor Exemplu"), ("Societatea Acme produce piese.",))
        == issues
    )


def test_leading_multiword_name_passes_when_the_label_holds_it() -> None:
    assert note_issues("Atlas Copco asigură aerul comprimat.", ("Atlas Copco",), ()) == []


def test_blank_note_leaves_no_field_and_is_asked_again(tmp_path: Path, live: FakeNotes) -> None:
    ws, job, thermal = _job(tmp_path)
    live.texts["tg-1"] = "   "
    live.texts["ts-2"] = "Importanța echipamentului:"
    run_measurements(ws, job)
    assert set(_notes(ws, job)) == set(thermal)

    live.texts.clear()
    run_measurements(ws, job)
    assert [item["id"] for item in live.requests[1]["items"]] == ["tg-1", "ts-2"]
    assert _notes(ws, job)["tg-1"] == PANEL
