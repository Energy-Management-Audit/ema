"""Invoice HTTP uploads preserve names and version a numbered slot."""

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from threading import Barrier

from fastapi.testclient import TestClient
from tests.workspace_jobs import create_job

from ema.api import create_app
from ema.api.mock import preview_pdf
from ema.clients.registry import create_client
from ema.core.errors import EmaError
from ema.core.workspace import Workspace
from ema.invoices import uploads
from ema.invoices.uploads import add_invoice_files

BASE = "http://127.0.0.1:8766"


def _session(ws: Workspace) -> tuple[TestClient, dict[str, str]]:
    client = TestClient(create_app(ws, 8766, launch_code="synthetic-code"), base_url=BASE)
    token = client.post("/session", json={"code": "synthetic-code"}).json()["csrf"]
    return client, {"x-ema-csrf": token}


def test_upload_names_numbering_replace_and_slot_revision(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    owner = create_client(ws, "Synthetic client")["id"]
    job = create_job(ws, "invoices", owner, 2026)
    client, headers = _session(ws)
    pdf = preview_pdf()
    response = client.post(
        f"/jobs/{job}/invoices/files",
        files=[
            ("files", ("first.pdf", pdf, "application/pdf")),
            ("files", ("second.pdf", pdf + b"\n% second", "application/pdf")),
        ],
        headers=headers,
    )
    assert response.status_code == 200, response.text
    added = response.json()["added"]
    assert [(item["slot"], item["file_name"]) for item in added] == [
        ("invoices/0001", "first.pdf"),
        ("invoices/0002", "second.pdf"),
    ]
    assert [ws.list_versions(job, item["slot"])[0].origin for item in added] == [
        "first.pdf",
        "second.pdf",
    ]
    replacement = client.post(
        f"/jobs/{job}/invoices/files?replace=invoices/0001",
        files={"files": ("updated.pdf", pdf + b"\n% updated", "application/pdf")},
        headers=headers,
    )
    assert replacement.status_code == 200, replacement.text
    assert replacement.json()["added"][0]["slot"] == "invoices/0001"
    versions = client.get(f"/jobs/{job}/slots/invoices/0001/versions").json()
    assert len(versions) == 2
    assert versions[0]["slot_revision"] == versions[1]["slot_revision"]
    stale = client.request(
        "DELETE",
        f"/jobs/{job}/slots/invoices/0001/versions/2",
        json={"confirm": True, "on_revision": versions[0]["slot_revision"] - 1},
        headers=headers,
    )
    assert stale.status_code == 409
    assert stale.json()["type"].endswith("stale_revision")
    removed = client.request(
        "DELETE",
        f"/jobs/{job}/slots/invoices/0001/versions/2",
        json={"confirm": True, "on_revision": versions[0]["slot_revision"]},
        headers=headers,
    )
    assert removed.status_code == 200
    assert ws.list_versions(job, "invoices/0001")[-1].origin == "first.pdf"
    second_revision = client.get(f"/jobs/{job}/slots/invoices/0002/versions").json()[0][
        "slot_revision"
    ]
    assert (
        client.request(
            "DELETE",
            f"/jobs/{job}/slots/invoices/0002/versions/1",
            json={"confirm": True, "on_revision": second_revision},
            headers=headers,
        ).status_code
        == 200
    )
    added_after_removal = client.post(
        f"/jobs/{job}/invoices/files",
        files={"files": ("third.pdf", pdf + b"\n% third", "application/pdf")},
        headers=headers,
    )
    assert added_after_removal.json()["added"][0]["slot"] == "invoices/0003"
    put = client.put(
        f"/jobs/{job}/slots/invoices/0004",
        json={"file_sha": added_after_removal.json()["added"][0]["sha"]},
        headers=headers,
    )
    assert put.status_code == 200
    assert (
        put.json()["slot_revision"]
        == client.get(f"/jobs/{job}/slots/invoices/0004/versions").json()[0]["slot_revision"]
    )


def test_concurrent_uploads_allocate_distinct_slots(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    ws = Workspace(tmp_path)
    owner = create_client(ws, "Synthetic client")["id"]
    job = create_job(ws, "invoices", owner, 2026)
    barrier = Barrier(2)
    original = uploads.store_upload

    def paired(*args: object) -> dict[str, object]:
        result = original(*args)
        barrier.wait(timeout=10)
        return result

    monkeypatch.setattr(uploads, "store_upload", paired)
    pdf = preview_pdf()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(add_invoice_files, ws, job, [("first.pdf", BytesIO(pdf))])
        second = pool.submit(
            add_invoice_files, ws, job, [("second.pdf", BytesIO(pdf + b"\n% second"))]
        )
        slots = {first.result()["added"][0]["slot"], second.result()["added"][0]["slot"]}
    assert slots == {"invoices/0001", "invoices/0002"}
    assert len(ws.list_slots(job, "invoices")) == 2


def test_upload_rejection_and_scoped_pdf_routes(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    ws = Workspace(tmp_path)
    owner = create_client(ws, "Synthetic client")["id"]
    job = create_job(ws, "invoices", owner, 2026)
    other = create_job(ws, "invoices", owner, 2026)
    client, headers = _session(ws)
    pdf = preview_pdf()
    response = client.post(
        f"/jobs/{job}/invoices/files",
        files=[
            ("files", ("notes.txt", b"notes", "text/plain")),
            ("files", ("invoice.pdf", pdf, "application/pdf")),
        ],
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["rejected"] == [
        {"file_name": "notes.txt", "code": "file_type", "reason": "Doar facturi PDF."}
    ]
    assert response.json()["added"][0]["slot"] == "invoices/0001"
    assert client.get(f"/jobs/{job}/invoices/file?slot=invoices/0001").content == pdf
    page = client.get(f"/jobs/{job}/invoices/page.png?slot=invoices/0001&page=1")
    assert page.status_code == 200 and page.content.startswith(b"\x89PNG")
    assert page.headers["x-content-type-options"] == "nosniff"
    assert (
        client.get(f"/jobs/{job}/invoices/page.png?slot=invoices/0001&page=999").status_code == 404
    )
    assert client.get(f"/jobs/{other}/invoices/file?slot=invoices/0001").status_code == 404
    assert client.get(f"/jobs/{job}/invoices/file?slot=dossier/0001").status_code == 400
    assert (
        client.get(f"/jobs/{job}/invoices/page.png?slot=invoices/0001&page=1&crop=bad").status_code
        == 422
    )

    def oversized(*_args: object) -> dict[str, object]:
        raise EmaError("file_too_large", "Fişierul este prea mare.", "")

    monkeypatch.setattr("ema.invoices.uploads.store_upload", oversized)
    too_large = client.post(
        f"/jobs/{job}/invoices/files", files={"files": ("big.pdf", pdf)}, headers=headers
    )
    assert too_large.json()["rejected"] == [
        {"file_name": "big.pdf", "code": "file_too_large", "reason": "Fişierul este prea mare."}
    ]
    invalid_replace = client.post(
        f"/jobs/{job}/invoices/files?replace=invoices/9999",
        files={"files": ("invoice.pdf", pdf)},
        headers=headers,
    )
    assert invalid_replace.status_code == 400
