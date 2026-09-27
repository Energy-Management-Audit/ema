"""CLIENT-P1's received files exercise the complete HTTP PIEE review journey."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lxml import etree
from pypdfium2 import PdfDocument

from conftest import artifacts_path
from ema.api import create_app
from ema.core.workspace import Workspace

pytestmark = pytest.mark.golden
BASE = "http://127.0.0.1:8766"


def _revision(client: TestClient, job: str) -> int:
    response = client.get(f"/jobs/{job}")
    assert response.status_code == 200
    return int(response.json()["revision"])


def _wait(client: TestClient, job: str, run: str) -> list[str]:
    response = client.get(f"/jobs/{job}/events")
    assert response.status_code == 200
    types = [
        line.removeprefix("event: ")
        for line in response.text.splitlines()
        if line.startswith("event: ")
    ]
    assert types[0] == "stage_started"
    assert types[-1] == "stage_finished"
    state = client.get(f"/jobs/{job}/status").json()
    assert next(row for row in state["runs"] if row["id"] == run)["state"] == "ready"
    return types


def _journey(  # noqa: PLR0915
    reference_library: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    stub_word: bool,
) -> tuple[Workspace, str, str]:
    base = next((reference_library / "piee/finished-programs").glob("*MODEL_2026.docx"))
    monkeypatch.setenv("EMA_PIEE_BASE_DOCUMENT", str(base))
    monkeypatch.setenv("EMA_PIEE_BASE_DIRECTORY", str(artifacts_path("s8", "base")))
    received = reference_library / "piee/cases/piee-case-a/received"
    sources = {
        "anexa": next(received.glob("Anexa*.xlsx")),
        "questionnaire": next(received.glob("Necesar*.xls")),
        "prelucrare": next(received.glob("*Prelucrare*.xls*")),
    }
    ws = Workspace(tmp_path / "workspace")
    client = TestClient(create_app(ws, 8766, launch_code="synthetic-code"), base_url=BASE)
    token = client.post("/session", json={"code": "synthetic-code"}).json()["csrf"]
    headers = {"X-Ema-CSRF": token}
    created = client.post("/clients", json={"name": "Synthetic"}, headers=headers)
    assert created.status_code == 201
    client_id = created.json()["id"]
    made = client.post(
        "/jobs",
        json={"type": "piee", "client": client_id, "year": 2026},
        headers=headers,
    )
    assert made.status_code == 200
    job = made.json()["id"]
    for slot, source in sources.items():
        with source.open("rb") as stream:
            uploaded = client.post(
                f"/clients/{client_id}/files",
                files={"file": (source.name, stream)},
                headers=headers,
            )
        assert uploaded.status_code == 201, uploaded.json().get("type")
        bound = client.put(
            f"/jobs/{job}/slots/{slot}",
            json={"file_sha": uploaded.json()["sha"]},
            headers=headers,
        )
        assert bound.status_code == 200

    imported = client.post(
        f"/jobs/{job}/piee/import",
        json={"on_revision": _revision(client, job)},
        headers=headers,
    )
    assert imported.status_code == 202, imported.json().get("type")
    _wait(client, job, imported.json()["run_id"])
    started = client.post(
        f"/jobs/{job}/piee/generate",
        json={"kind": "draft", "on_revision": _revision(client, job)},
        headers=headers,
    )
    assert started.status_code == 202, started.json().get("type")
    _wait(client, job, started.json()["run_id"])
    outputs = client.get(f"/jobs/{job}/outputs").json()
    draft = next(
        item
        for item in outputs
        if item["kind"] == "draft" and item["media_type"].endswith("document")
    )
    downloaded = client.get(f"/jobs/{job}/outputs/{draft['id']}")
    assert downloaded.status_code == 200 and downloaded.content.startswith(b"PK")
    api_draft_path = tmp_path / "http-draft.docx"
    api_draft_path.write_bytes(downloaded.content)
    refused = client.post(
        f"/jobs/{job}/export",
        json={"final": True, "output_id": draft["id"], "readiness_hash": "wrong", "confirm": True},
        headers=headers,
    )
    assert refused.status_code == 409 and refused.json()["type"] == "urn:ema:error:not_ready"
    conflicts = client.get(f"/jobs/{job}/conflicts").json()
    assert conflicts
    for field in conflicts:
        chosen = client.post(
            f"/jobs/{job}/conflicts/{field['id']}",
            json={"candidate_id": field["alternatives"][0]["id"], "on_revision": field["revision"]},
            headers=headers,
        )
        assert chosen.status_code == 200
    assert client.get(f"/jobs/{job}/conflicts").json() == []
    refreshed = client.post(
        f"/jobs/{job}/piee/generate",
        json={"kind": "draft", "on_revision": _revision(client, job)},
        headers=headers,
    )
    assert refreshed.status_code == 202
    _wait(client, job, refreshed.json()["run_id"])

    class StubWord:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def update_toc_pages(self, _docx: Path) -> None:
            pass

        def render_pdf(self, _docx: Path, pdf: Path) -> None:
            pdf.write_bytes(b"%PDF-1.4\n")

        def open_check(self, _docx: Path) -> None:
            pass

    if stub_word:
        monkeypatch.setattr(
            "ema.piee.review_workflow.word_automation", lambda _settings: StubWord()
        )
    word = client.post(
        f"/jobs/{job}/stages/piee_word",
        json={"on_revision": _revision(client, job)},
        headers=headers,
    )
    assert word.status_code == 202, word.json().get("type")
    _wait(client, job, word.json()["run_id"])
    final = next(
        item
        for item in reversed(client.get(f"/jobs/{job}/outputs").json())
        if item["kind"] == "final"
    )
    checks = client.get(f"/jobs/{job}/export/checks").json()
    assert checks["readiness"]["final_ok"]
    wrong_hash = client.post(
        f"/jobs/{job}/export",
        json={"final": True, "output_id": final["id"], "readiness_hash": "wrong", "confirm": True},
        headers=headers,
    )
    assert wrong_hash.status_code == 403
    assert wrong_hash.json()["type"] == "urn:ema:error:hash_mismatch"
    old_output = client.post(
        f"/jobs/{job}/export",
        json={
            "final": True,
            "output_id": draft["id"],
            "readiness_hash": checks["readiness_hash"],
            "confirm": True,
        },
        headers=headers,
    )
    assert old_output.status_code == 409
    assert old_output.json()["type"] == "urn:ema:error:output_stale"
    exported = client.post(
        f"/jobs/{job}/export",
        json={
            "final": True,
            "output_id": final["id"],
            "readiness_hash": checks["readiness_hash"],
            "confirm": True,
        },
        headers=headers,
    )
    assert exported.status_code == 200, exported.json().get("type")
    assert exported.json()["output_id"] == final["id"]

    cli_workspace = tmp_path / "cli-workspace"
    cli_env = os.environ.copy()
    cli_env["EMA_WORKSPACE"] = str(cli_workspace)
    cli = subprocess.run(
        [
            sys.executable,
            "-c",
            "from ema.cli import app; app()",
            "piee",
            "generate",
            "--client",
            "Synthetic",
            "--year",
            "2025",
            "--anexa",
            str(sources["anexa"]),
            "--necesar",
            str(sources["questionnaire"]),
            "--prelucrare",
            str(sources["prelucrare"]),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=cli_env,
    )
    cli_output = json.loads(cli.stdout)
    cli_ws = Workspace(cli_workspace)
    with cli_ws.connect() as db:
        cli_draft = db.execute(
            "SELECT relative_path FROM outputs WHERE job_id=? AND kind='draft' "
            "AND relative_path LIKE '%.docx'",
            (cli_output["job"],),
        ).fetchone()
    assert cli_draft is not None
    with (
        zipfile.ZipFile(api_draft_path) as http_package,
        zipfile.ZipFile(cli_ws.path(str(cli_draft["relative_path"]))) as cli_package,
    ):
        assert http_package.read("word/document.xml") == cli_package.read("word/document.xml")
    return ws, job, final["id"]


def test_CLIENT-P1_http_review_and_final_package(
    reference_library: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _journey(reference_library, tmp_path, monkeypatch, stub_word=True)


def test_CLIENT-P1_native_word_toc_pdf(
    reference_library: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.environ.get("EMA_WORD_SLOT") != "1":
        pytest.skip("Native Word slot required; package acceptance is separate")
    ws, job, output_id = _journey(reference_library, tmp_path, monkeypatch, stub_word=False)
    with ws.connect() as db:
        document = ws.path(
            str(
                db.execute("SELECT relative_path FROM outputs WHERE id=?", (output_id,)).fetchone()[
                    0
                ]
            )
        )
        pdf = ws.path(
            str(
                db.execute(
                    "SELECT relative_path FROM outputs WHERE job_id=? "
                    "AND relative_path LIKE '%.pdf' "
                    "ORDER BY seq DESC LIMIT 1",
                    (job,),
                ).fetchone()[0]
            )
        )
    assert pdf.is_file() and len(PdfDocument(pdf)) > 1
    with zipfile.ZipFile(document) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    assert root.xpath("//w:hyperlink[starts-with(@w:anchor, '_Toc')]", namespaces=namespaces)
