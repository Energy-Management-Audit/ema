"""S16a HTTP contract and local session integration on synthetic data."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import validate
from openapi_spec_validator import validate as validate_openapi
from pypdfium2 import PdfDocument

from ema.api import create_app
from ema.api.mock import preview_pdf, seed
from ema.api.provisional import PROVISIONAL, REASONS
from ema.audit.catalogue import CATALOGUE, AuditFact
from ema.core.jobs import StageOutcome, create_job, run_stage, status
from ema.core.review import propose
from ema.core.review.models import Evidence, PdfText
from ema.core.workspace import Workspace

PORT = 8766
BASE = f"http://127.0.0.1:{PORT}"


def session(ws: Workspace) -> tuple[TestClient, dict[str, str]]:
    client = TestClient(
        create_app(ws, PORT, launch_code="synthetic-code", dev_origin="http://127.0.0.1:5173"),
        base_url=BASE,
    )
    assert client.get("/jobs").status_code == 403
    assert client.post("/session", json={"code": "wrong"}).status_code == 403
    reply = client.post("/session", json={"code": "synthetic-code"})
    assert reply.status_code == 200
    assert client.post("/session", json={"code": "synthetic-code"}).status_code == 403
    assert client.post("/session", json={"code": ""}).status_code == 403
    return client, {"x-ema-csrf": reply.json()["csrf"]}


def evidence(name: str) -> Evidence:
    return Evidence(
        id=name,
        provenance="document",
        file_sha="synthetic",
        locator=PdfText(page=2, span="synthetic"),
        method="questionnaire",
        retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
        quote="Synthetic consumption: 120 MWh.",
        highlight="exact",
    )


def test_openapi_snapshot_and_provisional_mock(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    seed(ws)
    client, headers = session(ws)
    observed = client.get("/openapi.json").json()
    validate_openapi(observed)
    assert observed == json.loads(Path("openapi/ema.v1.json").read_text(encoding="utf-8"))
    assert observed["openapi"] == "3.1.0"
    mock = TestClient(create_app(ws, PORT, launch_code="mock-code", mock=True), base_url=BASE)
    mock_session = mock.post("/session", json={"code": "mock-code"})
    assert mock_session.status_code == 200
    audit_id = next(item["id"] for item in mock.get("/jobs").json() if item["type"] == "audit")
    for method, path in PROVISIONAL:
        operation = observed["paths"][path][method.lower()]
        assert operation["x-provisional"] == REASONS[path]
        if method != "GET" and "requestBody" in operation:
            content = operation["requestBody"]["content"]
            if "application/json" in content:
                request_content = content["application/json"]
                validate(request_content["example"], request_content["schema"])
            else:
                assert "multipart/form-data" in content
        url = path
        for key in (
            "client_id",
            "file_sha",
            "job_id",
            "stage",
            "section_id",
            "output_id",
            "invoice_id",
            "conflict_id",
            "run_id",
            "provider",
            "evidence_id",
        ):
            url = url.replace("{" + key + "}", "synthetic")
        if path.endswith("preview.pdf"):
            url = url.replace("synthetic", audit_id)
        reply = mock.request(method, url, headers={"x-ema-csrf": mock_session.json()["csrf"]})
        assert reply.status_code == 200, (method, path, reply.text)
        if path.endswith(".pdf"):
            assert reply.content.startswith(b"%PDF-")
            assert len(PdfDocument(reply.content)) == 1
        elif path.endswith(".png"):
            assert reply.content.startswith(b"\x89PNG")
        else:
            schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
            validate(reply.json(), schema)
        assert client.request(method, url, headers=headers).status_code == 501
    jobs = mock.get("/jobs").json()
    audit = next(item for item in jobs if item["type"] == "audit")
    for path, actual in (
        ("/jobs", "/jobs"),
        ("/jobs/{job_id}/fields", f"/jobs/{audit['id']}/fields"),
        ("/evidence/{evidence_id}/quote", "/evidence/audit-example/quote"),
    ):
        response = mock.get(actual)
        assert response.status_code == 200
        schema = observed["paths"][path]["get"]["responses"]["200"]["content"]["application/json"][
            "schema"
        ]
        validate(response.json(), {**schema, "components": observed["components"]})


def test_session_checks_cover_json_sse_and_download(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    app = create_app(ws, PORT, launch_code="launch", dev_origin="http://127.0.0.1:5173")
    client = TestClient(app, base_url=BASE)
    for path in (
        "/jobs",
        f"/jobs/{job}/events",
        f"/jobs/{job}/outputs/missing",
        "/evidence/missing/quote",
    ):
        assert client.get(path).status_code == 403
    assert client.get("/health", headers={"host": "evil.example"}).status_code == 421
    assert (
        client.post(
            "/session", json={"code": "launch"}, headers={"origin": "http://evil.example"}
        ).status_code
        == 403
    )
    response = client.post(
        "/session", json={"code": "launch"}, headers={"origin": "http://127.0.0.1:5173"}
    )
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert client.get("/jobs", headers={"origin": "http://evil.example"}).status_code == 403
    assert client.post(f"/jobs/{job}/cancel").status_code == 403
    assert (
        client.post(
            f"/jobs/{job}/cancel", headers={"x-ema-csrf": response.json()["csrf"]}
        ).status_code
        == 200
    )


def test_frozen_job_slot_review_and_section_routes(tmp_path: Path) -> None:  # noqa: PLR0915
    ws = Workspace(tmp_path / "workspace")
    client, headers = session(ws)
    assert (
        client.post(
            "/jobs", json={"type": "audit", "client": "synthetic", "year": 2026}
        ).status_code
        == 403
    )
    client_id = client.post("/clients", json={"name": "Synthetic Client"}, headers=headers).json()[
        "id"
    ]
    created = client.post(
        "/jobs", json={"type": "audit", "client": client_id, "year": 2026}, headers=headers
    )
    assert created.status_code == 200
    job = created.json()["id"]
    assert len(client.get("/jobs").json()) == 1
    assert client.get(f"/jobs/{job}").json()["type"] == "audit"
    assert client.get(f"/jobs/{job}").json()["revision"] == 1
    assert client.get(f"/jobs/{job}/status").json()["state"] == "created"
    assert client.get(f"/jobs/{job}/status").json()["revision"] == 1
    assert client.post(f"/jobs/{job}/cancel", headers=headers).json() == {"cancelled": True}

    source = tmp_path / "source.txt"
    source.write_text("Synthetic document", encoding="utf-8")
    sha = ws.add_file(client_id, source)
    slot = f"/jobs/{job}/slots/dossier/001"
    first = client.put(slot, json={"file_sha": sha}, headers=headers)
    assert first.status_code == 200
    assert client.get(f"/jobs/{job}/slots").json() == ["dossier/001"]
    assert client.get(f"{slot}/versions").json()[0]["file_sha"] == sha
    with ws.connect() as db:
        slot_revision = db.execute(
            "SELECT revision FROM slots WHERE job_id=? AND name=?", (job, "dossier/001")
        ).fetchone()[0]
    assert (
        client.request(
            "DELETE",
            f"{slot}/versions/1",
            json={"confirm": True, "on_revision": slot_revision},
            headers=headers,
        ).status_code
        == 200
    )

    field = propose(
        ws, job, AuditFact.COMPANY_NAME.value, "Before", [evidence("source-1")], state="extracted"
    )
    fields = client.get(f"/jobs/{job}/fields", params={"status": "pending"}).json()
    assert len(fields) == 1 and fields[0]["id"] == field.id
    assert client.get("/evidence/source-1/quote").json()["quote"].startswith("Synthetic")
    assert client.get(f"/jobs/{job}/conflicts").json() == []
    number = propose(ws, job, "synthetic_number", 12, [], state="extracted")
    invalid = client.post(
        f"/jobs/{job}/fields/{number.id}/decide",
        json={"action": "correct", "value": "nonsense", "on_revision": number.revision},
        headers=headers,
    )
    assert invalid.status_code == 400
    decision = client.post(
        f"/jobs/{job}/fields/{field.id}/decide",
        json={"action": "correct", "value": "After", "on_revision": field.revision},
        headers=headers,
    )
    assert decision.status_code == 200
    assert client.get(f"/jobs/{job}/log").json()[0]["id"] == decision.json()["id"]
    assert (
        client.post(f"/jobs/{job}/log/{decision.json()['id']}/undo", headers=headers).status_code
        == 200
    )
    revised = client.get(f"/jobs/{job}/fields").json()[0]
    assert revised["value"] == "Before"
    accepted = client.post(
        f"/jobs/{job}/fields/accept-batch",
        json={"fields": [[field.id, revised["revision"]]]},
        headers=headers,
    )
    assert accepted.status_code == 200 and len(accepted.json()) == 1

    sections = client.get(f"/jobs/{job}/sections").json()
    assert len(sections) == len(CATALOGUE)
    section = sections[0]["section_id"]
    assert (
        client.patch(
            f"/jobs/{job}/sections/{section}",
            json={"status": "n/a", "on_revision": 0},
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/jobs/{job}/sections/{section}",
            json={"status": "n/a", "confirm": True, "on_revision": 0},
            headers=headers,
        ).status_code
        == 200
    )
    assert client.get(f"/jobs/{job}/export/checks").json()["readiness"]["final_ok"] is False
    assert (
        client.post(
            f"/jobs/{job}/export",
            json={
                "final": True,
                "confirm": True,
                "output_id": "synthetic",
                "readiness_hash": "synthetic",
            },
            headers=headers,
        ).status_code
        == 409
    )
    with ws.connect() as db:
        job_revision = db.execute("SELECT revision FROM jobs WHERE id=?", (job,)).fetchone()[0]
    assert (
        client.request(
            "DELETE",
            f"/jobs/{job}",
            json={"confirm": False, "on_revision": job_revision},
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.request(
            "DELETE",
            f"/jobs/{job}",
            json={"confirm": True, "on_revision": job_revision},
            headers=headers,
        ).status_code
        == 200
    )


def test_http_rerun_undo_and_synthetic_final_export(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    field = propose(
        ws, job, AuditFact.COMPANY_NAME.value, "Before", [evidence("before")], state="extracted"
    )
    client, headers = session(ws)
    correction = client.post(
        f"/jobs/{job}/fields/{field.id}/decide",
        json={"action": "correct", "value": "Corrected", "on_revision": field.revision},
        headers=headers,
    )
    assert correction.status_code == 200
    propose(ws, job, AuditFact.COMPANY_NAME.value, "Before", [evidence("rerun")], state="extracted")
    assert len(client.get(f"/jobs/{job}/conflicts").json()) == 1
    assert (
        client.post(f"/jobs/{job}/log/{correction.json()['id']}/undo", headers=headers).status_code
        == 400
    )
    assert (
        client.post(
            f"/jobs/{job}/export",
            json={
                "final": True,
                "output_id": "synthetic",
                "readiness_hash": "synthetic",
                "confirm": True,
            },
            headers=headers,
        ).status_code
        == 409
    )
    for section in CATALOGUE:
        current_revision = next(
            state["revision"]
            for state in client.get(f"/jobs/{job}/sections").json()
            if state["section_id"] == section.id
        )
        reply = client.patch(
            f"/jobs/{job}/sections/{section.id}",
            json={"status": "n/a", "confirm": True, "on_revision": current_revision},
            headers=headers,
        )
        assert reply.status_code == 200
    assert client.get(f"/jobs/{job}/export/checks").json()["readiness"]["final_ok"] is False
    current = client.get(f"/jobs/{job}/fields").json()[0]
    choice = current["alternatives"][0]["id"]
    resolved = client.post(
        f"/jobs/{job}/fields/{field.id}/decide",
        json={"action": "choose", "alternative": choice, "on_revision": current["revision"]},
        headers=headers,
    )
    assert resolved.status_code == 200
    assert (
        client.post(f"/jobs/{job}/log/{resolved.json()['id']}/undo", headers=headers).status_code
        == 200
    )
    assert client.get(f"/jobs/{job}/export/checks").json()["readiness"]["final_ok"] is False
    current = client.get(f"/jobs/{job}/fields").json()[0]
    assert (
        client.post(
            f"/jobs/{job}/fields/{field.id}/decide",
            json={"action": "choose", "alternative": choice, "on_revision": current["revision"]},
            headers=headers,
        ).status_code
        == 200
    )
    checks = client.get(f"/jobs/{job}/export/checks").json()
    assert checks["readiness"]["final_ok"] is True

    def save(ctx):  # type: ignore[no-untyped-def]
        path = ctx.artifact_dir() / "synthetic.pdf"
        path.write_bytes(preview_pdf())
        ctx.save_output(path, "synthetic.pdf", kind="final")
        return StageOutcome()

    run_stage(ws, job, "render", save)
    deadline = time.monotonic() + 5
    while status(ws, job).state == "running" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert status(ws, job).runs[-1]["state"] == "ready"
    with ws.connect() as db:
        output_id = str(db.execute("SELECT id FROM outputs WHERE job_id=?", (job,)).fetchone()[0])
    assert client.get(f"/jobs/{job}/outputs/{output_id}").content == preview_pdf()
    checks = client.get(f"/jobs/{job}/export/checks").json()
    assert (
        client.post(
            f"/jobs/{job}/export",
            json={
                "final": True,
                "output_id": output_id,
                "readiness_hash": checks["readiness_hash"],
            },
            headers=headers,
        ).status_code
        == 403
    )
    result = client.post(
        f"/jobs/{job}/export",
        json={
            "final": True,
            "output_id": output_id,
            "readiness_hash": checks["readiness_hash"],
            "confirm": True,
        },
        headers=headers,
    )
    assert result.status_code == 200, result.text
    assert result.json() == {"output_id": output_id}
    assert (ws.root / "exports" / f"{job}-{output_id}.pdf").read_bytes() == preview_pdf()
