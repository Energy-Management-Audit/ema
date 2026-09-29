"""P3 boundary, cancellation, model and Word-marker regressions."""

import ast
import json
from dataclasses import replace
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest
from tests.unit.audit.test_intake import _checklist
from tests.unit.test_s17b_clients_routes import _session
from typer.testing import CliRunner

from ema.api.errors import STATUS
from ema.audit.stages import new_audit
from ema.cli import _app
from ema.clients.registry import create_client
from ema.core.config import load_settings
from ema.core.errors import EmaError
from ema.core.jobs import cancel, create_job, run_stage, status, subscribe
from ema.core.llm import providers
from ema.core.llm.models import curated_models
from ema.core.llm.providers import OpenAIProvider
from ema.core.llm.replay import ReplayProvider
from ema.core.workspace import Workspace
from ema.invoices import extract_batch
from ema.invoices.composition import build_invoice_processor


def test_every_literal_raised_code_has_an_explicit_http_status():
    codes = set()
    for source in Path("src/ema").rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"EmaError", "OfficeError"}
                and node.args
            ):
                code = node.args[0]
                if isinstance(code, ast.Constant) and isinstance(code.value, str):
                    codes.add(code.value)
    assert codes - STATUS.keys() == set()
    assert STATUS["output_stale"] == STATUS["approval_required"] == 409
    assert STATUS["use_audit_intake"] == 409
    assert STATUS["client_unknown"] == 404
    assert STATUS["piee_annex_year"] == STATUS["piee_sources_incomplete"] == 422


def test_unknown_client_is_refused_without_job_or_orphan_client(tmp_path):
    ws = Workspace(tmp_path / "workspace")
    for create in (
        lambda: create_job(ws, "audit", "unknown", 2026),
        lambda: new_audit(ws, "87654321", 2026),
    ):
        with pytest.raises(EmaError) as error:
            create()
        assert error.value.code == "client_unknown"
    with ws.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM clients").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
    assert not list((ws.root / "clients").glob("*/jobs/*"))


def test_audit_cli_new_add_run_status_and_generic_intake_refusal(tmp_path, monkeypatch):
    ws = Workspace(tmp_path / "workspace")
    client = create_client(ws, "Synthetic", "RO 12345678")
    monkeypatch.setenv("EMA_WORKSPACE", str(ws.root))
    runner = CliRunner()
    created = runner.invoke(_app, ["audit", "new", "--client", "12345678", "--year", "2026"])
    assert created.exit_code == 0, created.output
    job = created.stdout.strip()
    checklist = tmp_path / "0.Necesar info.xlsx"
    _checklist(checklist)
    added = runner.invoke(_app, ["audit", "add", job, str(checklist)])
    assert added.exit_code == 0, added.output
    refused = runner.invoke(_app, ["intake", job, "dossier"])
    assert refused.exit_code == 1
    assert isinstance(refused.exception, EmaError)
    assert refused.exception.code == "use_audit_intake"
    started = runner.invoke(_app, ["audit", "run", job, "intake"])
    assert started.exit_code == 0, started.output
    view = runner.invoke(_app, ["audit", "status", job])
    assert view.exit_code == 0, view.output
    assert json.loads(view.stdout)["runs"][0]["stage"] == "intake"
    with ws.connect() as db:
        assert (
            db.execute("SELECT client_slug FROM jobs WHERE id=?", (job,)).fetchone()[0]
            == client["id"]
        )


def test_cancellation_stops_after_blocked_pdf(tmp_path, monkeypatch):
    ws = Workspace(tmp_path / "workspace")
    person = create_client(ws, "Synthetic", "12345678")
    job = create_job(ws, "invoices", person["id"], None)
    for index in range(2):
        source = tmp_path / f"{index}.pdf"
        source.write_bytes(f"synthetic {index}".encode())
        ws.set_slot(job, f"invoices/{index:04d}", ws.add_file(person["id"], source))
    entered, release = Event(), Event()
    read = []

    class Reader:
        def read(self, path):
            read.append(path)
            entered.set()
            assert release.wait(5)
            raise EmaError("pdf_read_failed", "Citirea a eşuat.", "synthetic")

    processor = build_invoice_processor(load_settings(ws))
    monkeypatch.setattr(processor, "_reader", Reader())
    monkeypatch.setattr("ema.invoices.build_invoice_processor", lambda *_: processor)
    run = run_stage(ws, job, "invoices", extract_batch)
    try:
        assert entered.wait(5)
        cancel(ws, job)
    finally:
        release.set()
    list(subscribe(ws, job))
    assert len(read) == 1
    assert next(item for item in status(ws, job).runs if item["id"] == run)["state"] == "cancelled"


def test_retired_routes_are_absent(tmp_path):
    ws = Workspace(tmp_path / "workspace")
    http, headers = _session(ws)
    person = create_client(ws, "Synthetic", "12345678")
    job = create_job(ws, "audit", person["id"], 2026)
    for path in [
        f"/jobs/{job}/export/draft",
        f"/jobs/{job}/sections/ch2.date_generale/na-proposal",
    ]:
        assert http.post(path, headers=headers, json={"on_revision": 1}).status_code == 404
    assert (
        http.post(
            "/jobs", headers=headers, json={"type": "reporting", "client": person["id"]}
        ).status_code
        == 422
    )


def test_replay_identity_comes_from_recording(tmp_path):
    model = next(model for model in curated_models() if model.provider == "openai")
    recording = tmp_path / "recording.json"
    recording.write_text(
        json.dumps(
            {
                "source": "recorded",
                "format": "openai-chat-completions",
                "responses": [{"model": model.id}],
            }
        ),
        encoding="utf-8",
    )
    replay = ReplayProvider(recording)
    assert replay.model_id == model.id
    assert replay.provider_name == "openai"


def test_model_request_options_follow_curated_settings(monkeypatch):
    configured = next(model for model in curated_models() if model.provider == "openai")
    configured = replace(
        configured, id="release-model", request_options={"reasoning_effort": "low"}
    )
    monkeypatch.setattr(providers, "selected_model", lambda *_: configured)
    requests = []

    def create(**request):
        requests.append(request)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="done", tool_calls=None))],
            usage=None,
        )

    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    provider.respond(configured.id, [], (), synthetic=True)
    assert requests[0]["reasoning_effort"] == "low"


def test_error_messages_always_use_handoff_diacritics():
    assert (
        EmaError("value_invalid", "Secțiune și informații", "").user_message_ro
        == "Secţiune şi informaţii"
    )


def test_every_literal_ema_error_message_uses_handoff_diacritics():
    messages = []
    for source in Path("src/ema").rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "EmaError"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
            ):
                messages.append(node.args[1].value)
    assert len(messages) > 50
    for message in messages:
        assert not set("șțȘȚ") & set(EmaError("synthetic", message, "").user_message_ro)
