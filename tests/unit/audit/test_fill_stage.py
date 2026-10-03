"""The Fill stage over the synthetic S12 dossier: one extraction, failure isolation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from tests.workspace_jobs import create_job

from ema.api.job_routes import start_named_stage
from ema.audit import fill_stage
from ema.audit.draft_schema import SECTION_FACTS
from ema.audit.fill_stage import FillSummary, fill_sections, settings_provider
from ema.audit.fill_tools import FillTools
from ema.audit.read import read_dossier
from ema.audit.sections import get_status
from ema.core.config import Settings
from ema.core.errors import EmaError
from ema.core.jobs import get_job, status, subscribe
from ema.core.llm import curated_models, default_model
from ema.core.llm.types import Exchange, Provider, ToolSpec
from ema.core.workspace import Workspace

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
SECTION = "ch2.date_generale"
OPENAI_MODEL = next(model.id for model in curated_models() if model.provider == "openai")


def write_pdf(path: Path, line: str) -> Path:
    content = f"BT /F1 12 Tf 50 700 Td ({line}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    start = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    )
    path.write_bytes(data)
    return path


def synthetic_dossier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Workspace, str]:
    """The S12 made-up dossier, stored in dossier slots as the stage reads it."""
    ws = Workspace(tmp_path / "workspace")
    # The recording includes job-owned evidence IDs.
    with monkeypatch.context() as fixed_job:
        fixed_job.setattr("ema.core.jobs.uuid.uuid4", lambda: UUID(int=19))
        job = create_job(ws, "audit", "made-up", 2026)
    read_dossier(ws, job, FIXTURES / "audit/synthetic_necesar.xlsx")
    fisa = tmp_path / "fisa.txt"
    fisa.write_text(
        "Firma Exemplu SRL are sediul în Alba. Activitate: vopsire industrială.", encoding="utf-8"
    )
    permit = write_pdf(
        tmp_path / "permit.pdf", "Autorizatie pentru Firma Exemplu SRL. Suprafata: 500 m2."
    )
    for source in (fisa, permit):
        ws.set_slot(job, f"dossier/{source.name}", ws.add_file("made-up", source))
    return ws, job


def use_provider(monkeypatch: pytest.MonkeyPatch, provider: Provider, model: str) -> None:
    monkeypatch.setattr(fill_stage, "settings_provider", lambda settings: (provider, model))


class LiveProvider:
    """A provider that is not a replay: it answers every extraction or fails with one error."""

    name = "openai"

    def __init__(self, failure: EmaError | None = None, answer: str = "") -> None:
        self.failure = failure
        self.answer = answer or json.dumps({"facts": [], "missing": []})
        self.tasks: list[str] = []

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
        del model, tools, schema, max_output_tokens, synthetic, prompt_version, attachments
        self.tasks.append(str(messages[1]["content"]))
        if self.failure is not None:
            raise self.failure
        return Exchange(self.answer, (), 10, 10)


def run_events(ws: Workspace, run: str) -> list[tuple[str, dict[str, Any]]]:
    with ws.connect() as db:
        rows = db.execute(
            "SELECT type,payload FROM job_events WHERE run_id=? ORDER BY seq", (run,)
        ).fetchall()
    return [(str(row["type"]), json.loads(row["payload"])) for row in rows]


def test_bad_dossier_file_is_recorded_once_and_other_sections_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMA_AI_CLIENT_LIVE", "1")
    ws, job = synthetic_dossier(tmp_path, monkeypatch)
    provider = LiveProvider()
    use_provider(monkeypatch, provider, OPENAI_MODEL)
    original = fill_stage.dossier_documents

    def bad_file(ws: Workspace, job: str, slots: dict[str, str]) -> dict[str, Any]:
        if "permit.pdf" in slots:
            raise EmaError("file_invalid", "Fişier invalid.", "permit.pdf")
        return original(ws, job, slots)

    monkeypatch.setattr(fill_stage, "dossier_documents", bad_file)
    summary = fill_sections(ws, job, [SECTION, "ch2.localizare"])

    assert summary.failed == {"permit.pdf": "file_invalid"}
    assert summary.sections == {SECTION: "done", "ch2.localizare": "done"}
    assert len(provider.tasks) == 1
    assert "Fişiere:\nF1: fisa.txt\n[F1 p.1]\n" in provider.tasks[0]
    assert "permit" not in provider.tasks[0]
    with ws.connect() as db:
        log = (ws.job_path(db, job) / "log.jsonl").read_text(encoding="utf-8")
    assert log.count('"file": "permit.pdf", "code": "file_invalid"') == 1


def test_failed_section_setup_is_isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMA_AI_CLIENT_LIVE", "1")
    ws, job = synthetic_dossier(tmp_path, monkeypatch)
    provider = LiveProvider()
    use_provider(monkeypatch, provider, OPENAI_MODEL)
    original = fill_stage.record_applicability

    def bad_setup(ws: Workspace, job: str, section: str) -> Any:
        if section == SECTION:
            raise EmaError("applicability_invalid", "Aplicabilitate invalidă.", section)
        return original(ws, job, section)

    monkeypatch.setattr(fill_stage, "record_applicability", bad_setup)
    summary = fill_sections(ws, job, [SECTION, "ch2.localizare"])

    assert summary.failed == {SECTION: "applicability_invalid"}
    assert summary.sections == {"ch2.localizare": "done"}
    assert len(provider.tasks) == 1
    assert "audit.location — " in provider.tasks[0]
    assert "audit.company_name" not in provider.tasks[0]


def test_fill_is_a_job_stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws, job = synthetic_dossier(tmp_path, monkeypatch)
    use_provider(monkeypatch, LiveProvider(), OPENAI_MODEL)
    revision = int(str(get_job(ws, job)["revision"]))

    # The API route and `ema audit run <job> fill` both start it through start_audit_stage.
    run = start_named_stage(ws, job, "fill", revision)
    for _ in subscribe(ws, job):
        pass

    assert next(item for item in status(ws, job).runs if item["id"] == run)["state"] == "ready"


def test_switch_off_fails_each_section_with_client_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EMA_AI_CLIENT_LIVE", raising=False)
    ws, job = synthetic_dossier(tmp_path, monkeypatch)
    provider = LiveProvider()
    use_provider(monkeypatch, provider, OPENAI_MODEL)

    summary = fill_sections(ws, job, [SECTION, "ch2.localizare"])

    assert summary.failed == {
        SECTION: "ai_client_disabled",
        "ch2.localizare": "ai_client_disabled",
    }
    assert provider.tasks == []
    events = run_events(ws, summary.run)
    assert [kind for kind, _ in events].count("item_failed") == 2
    assert events[-1] == (
        "stage_finished",
        {"state": "ready", "publication": "current", "item_failures": 2, "warnings": 0},
    )


def test_a_provider_failure_fails_each_applicable_section_and_is_logged_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMA_AI_CLIENT_LIVE", "1")
    ws, job = synthetic_dossier(tmp_path, monkeypatch)
    quota = EmaError("ai_quota_day", "Cota zilnică a furnizorului AI s-a epuizat.", OPENAI_MODEL)
    provider = LiveProvider(quota)
    use_provider(monkeypatch, provider, OPENAI_MODEL)

    summary = fill_sections(ws, job, [SECTION, "ch2.localizare"])

    assert summary == FillSummary(
        summary.run, {}, {SECTION: "ai_quota_day", "ch2.localizare": "ai_quota_day"}, ()
    )
    assert len(provider.tasks) == 1
    kind, payload = run_events(ws, summary.run)[-1]
    assert (kind, payload["item_failures"]) == ("stage_finished", 2)
    with ws.connect() as db:
        log = (ws.job_path(db, job) / "log.jsonl").read_text("utf-8")
    assert log.count('"event": "fill_failed"') == 1
    assert '"sections": ["ch2.date_generale", "ch2.localizare"], "code": "ai_quota_day"' in log


def test_unknown_section_is_refused_before_the_stage(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "made-up", 2026)

    with pytest.raises(EmaError) as refused:
        fill_sections(ws, job, ["ch5.masuratori"])
    assert refused.value.code == "section_missing"


def test_settings_provider_needs_the_live_switch_and_picks_the_standard_model() -> None:
    with pytest.raises(EmaError) as offline:
        settings_provider(Settings(provider="openai", openai_api_key="key", llm_live=False))
    assert offline.value.code == "ai_offline"
    with pytest.raises(EmaError) as missing:
        settings_provider(Settings(provider=None))
    assert missing.value.code == "provider_invalid"
    provider, model = settings_provider(
        Settings(provider="openai", openai_api_key="key", llm_live=True)
    )
    assert provider.name == "openai"
    assert model == default_model("openai").id
    _, gemini = settings_provider(Settings(provider="gemini", gemini_api_key="key", llm_live=True))
    assert gemini == "gemini-3.8-flash"
    _, chosen = settings_provider(
        Settings(provider="openai", model=OPENAI_MODEL, openai_api_key="key", llm_live=True)
    )
    assert chosen == OPENAI_MODEL


def test_default_run_covers_every_applicable_chapter_two_three_section(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMA_AI_CLIENT_LIVE", "1")
    ws, job = synthetic_dossier(tmp_path, monkeypatch)
    # A trigger fact recorded as absent makes its section n/a.
    FillTools(ws, job, "ch2.manager", {}).mark_missing({"key": "audit.energy_manager"})
    provider = LiveProvider()
    use_provider(monkeypatch, provider, OPENAI_MODEL)

    summary = fill_sections(ws, job)

    assert summary.not_applicable == ("ch2.manager",)
    assert get_status(ws, job, "ch2.manager").applicability is False
    assert set(summary.sections) == set(SECTION_FACTS) - {"ch2.manager"}
    # One extraction for every section; the old per-section loop made one run each.
    assert len(provider.tasks) == 1
    assert summary.extracted is not None and summary.extracted.calls == 1


def test_default_model_is_the_first_standard_model_of_the_provider() -> None:
    assert default_model("gemini").id == "gemini-3.8-flash"
    with pytest.raises(EmaError) as unknown:
        default_model("missing")
    assert unknown.value.code == "model_unknown"
