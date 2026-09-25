"""Streamed upload validation and client-bound download paths."""

import io
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ema.api import create_app
from ema.api.job_routes import validate_slot
from ema.api.mock import preview_pdf
from ema.clients.files import store_upload
from ema.clients.registry import create_client
from ema.core.errors import EmaError
from ema.core.jobs import StageOutcome, create_job, run_stage, status, subscribe
from ema.core.review.models import Evidence, PdfRegion
from ema.core.workspace import Workspace

BASE = "http://127.0.0.1:8766"


def _client(ws: Workspace) -> tuple[TestClient, dict[str, str]]:
    client = TestClient(create_app(ws, 8766, launch_code="synthetic-code"), base_url=BASE)
    token = client.post("/session", json={"code": "synthetic-code"}).json()["csrf"]
    return client, {"X-Ema-CSRF": token}


def test_stream_cap_and_types(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    identity = create_client(ws, "Synthetic")
    client_id = identity["id"]
    with pytest.raises(EmaError) as too_large:
        store_upload(ws, client_id, io.BytesIO(b"123456"), "notes.txt", limit=5)
    assert too_large.value.code == "file_too_large"
    stored = store_upload(ws, client_id, io.BytesIO(b"12345"), "notes.txt", limit=5)
    assert stored["size_bytes"] == 5
    for name, payload in (
        ("empty.pdf", b""),
        ("unknown.bin", preview_pdf()),
        ("mismatch.xlsx", preview_pdf()),
    ):
        with pytest.raises(EmaError) as invalid:
            store_upload(ws, client_id, io.BytesIO(payload), name)
        assert invalid.value.code == "file_type"
    assert list(ws.path("temp").iterdir()) == []


def test_multipart_dedupe_cross_client_and_binary_download(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    first = create_client(ws, "First")["id"]
    second = create_client(ws, "Second")["id"]
    job = create_job(ws, "audit", first, 2026)
    other_job = create_job(ws, "audit", second, 2026)
    client, headers = _client(ws)
    document = preview_pdf()
    response = client.post(
        f"/clients/{first}/files",
        files={"file": ("first.pdf", document, "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    sha = response.json()["sha"]
    repeated = client.post(
        f"/clients/{first}/files",
        files={"file": ("renamed.pdf", document, "application/pdf")},
        headers=headers,
    )
    assert repeated.json()["sha"] == sha
    assert repeated.json()["name"] == "first.pdf"
    versions = client.get(f"/clients/{first}/files/{sha}/versions")
    assert versions.json() == [
        {"version": 1, "sha": sha, "name": "first.pdf", "size_bytes": len(document)}
    ]
    assert (
        client.put(
            f"/jobs/{other_job}/slots/anexa", json={"file_sha": sha}, headers=headers
        ).status_code
        == 404
    )
    assert client.put(
        f"/jobs/{job}/slots/../escape", json={"file_sha": sha}, headers=headers
    ).status_code in {400, 404}
    bound = client.put(f"/jobs/{job}/slots/anexa", json={"file_sha": sha}, headers=headers)
    assert bound.status_code == 200

    def produce(ctx):  # type: ignore[no-untyped-def]
        path = ctx.artifact_dir() / "draft.pdf"
        path.write_bytes(document)
        ctx.save_output(path, "draft.pdf", kind="final")
        return StageOutcome()

    run = run_stage(ws, job, "synthetic", produce)
    for _ in subscribe(ws, job):
        pass
    assert next(item for item in status(ws, job).runs if item["id"] == run)["state"] == "ready"
    output_id = client.get(f"/jobs/{job}/outputs").json()[0]["id"]
    download = client.get(f"/jobs/{job}/outputs/{output_id}")
    assert download.content == document
    assert download.headers["content-type"] == "application/pdf"
    assert 'filename="draft.pdf"' in download.headers["content-disposition"]
    assert download.headers["x-content-type-options"] == "nosniff"
    assert client.get(f"/jobs/{other_job}/outputs/{output_id}").status_code == 404
    with ws.connect() as db:
        relative = db.execute(
            "SELECT relative_path FROM outputs WHERE id=?", (output_id,)
        ).fetchone()[0]
    ws.path(relative).write_bytes(b"modified")
    assert client.get(f"/jobs/{job}/outputs").json()[0]["edited_externally"]
    assert client.get(f"/jobs/{job}/outputs/{output_id}").status_code == 409


def test_evidence_png_uses_client_bound_pdf(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    client_id = create_client(ws, "Synthetic")["id"]
    job = create_job(ws, "audit", client_id, 2026)
    source = tmp_path / "synthetic.pdf"
    source.write_bytes(preview_pdf())
    sha = ws.add_file(client_id, source)
    evidence = Evidence(
        id="synthetic-evidence",
        provenance="document",
        file_sha=sha,
        locator=PdfRegion(page=1, bbox=(1, 1, 40, 40)),
        method="invoice",
        retrieved_at=datetime.now(UTC),
        highlight="exact",
    )
    with ws.connect() as db:
        db.execute(
            "INSERT INTO evidence(id,job_id,data) VALUES (?,?,?)",
            (evidence.id, job, evidence.model_dump_json()),
        )
    client, _headers = _client(ws)
    for path in ("snippet.png?highlight=1", "page.png"):
        response = client.get(f"/evidence/{evidence.id}/{path}")
        assert response.status_code == 200, response.json() if response.status_code != 200 else ""
        assert response.content.startswith(b"\x89PNG")
        assert response.headers["content-type"] == "image/png"
        assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize(
    ("job_type", "valid", "other"),
    [
        ("piee", "anexa", "dossier/file.pdf"),
        ("audit", "dossier/folder/file.pdf", "questionnaire"),
        ("invoices", "invoices/0001", "anexa"),
        ("reporting", None, "invoices/0001"),
    ],
)
def test_http_slot_allowlist_by_job_type(
    tmp_path: Path,
    job_type: str,
    valid: str | None,
    other: str,
) -> None:
    ws = Workspace(tmp_path)
    client_id = create_client(ws, "Synthetic")["id"]
    job = create_job(ws, job_type, client_id, 2026)  # type: ignore[arg-type]
    source = tmp_path / "synthetic.pdf"
    source.write_bytes(preview_pdf())
    sha = ws.add_file(client_id, source)
    client, headers = _client(ws)
    if valid is not None:
        assert (
            client.put(
                f"/jobs/{job}/slots/{valid}",
                json={"file_sha": sha},
                headers=headers,
            ).status_code
            == 200
        )
    refused = client.put(
        f"/jobs/{job}/slots/{other}",
        json={"file_sha": sha},
        headers=headers,
    )
    assert refused.status_code == 400
    assert refused.json()["type"] == "urn:ema:error:invalid_slot"
    for traversal in ("dossier/../file.pdf", "visit/./file.pdf", "dossier/a\\b.pdf"):
        with pytest.raises(EmaError) as invalid:
            validate_slot(job_type, traversal)
        assert invalid.value.code == "invalid_slot"
