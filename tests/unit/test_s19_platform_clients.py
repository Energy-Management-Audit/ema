"""P3 client upload retention and revision-safe identity regressions."""

import io
import json
from pathlib import Path
from threading import Event, Thread

import pytest
from tests.unit.test_s17b_clients_routes import _session

from ema.clients import anaf
from ema.clients.files import file_versions, store_upload
from ema.clients.profile import profile
from ema.clients.registry import create_client, get_client, update_client
from ema.core.backup import backup, restore
from ema.core.errors import EmaError
from ema.core.jobs import create_job
from ema.core.workspace import Workspace
from ema.core.workspace.gc import collect_garbage


@pytest.mark.parametrize("attached", [False, True])
def test_upload_survives_gc_backup_and_last_job_deletion(tmp_path: Path, attached: bool) -> None:
    ws = Workspace(tmp_path / "workspace")
    client = create_client(ws, "Example", "12345678")
    cid = client["id"]
    content = b"%PDF-1.4\nsynthetic upload\n%%EOF\n"
    upload = store_upload(ws, cid, io.BytesIO(content), "source.pdf")
    if attached:
        job = create_job(ws, "audit", cid, 2026)
        ws.set_slot(job, "dossier/source.pdf", upload["sha"])
        ws.delete_job(job)
    with ws.connect() as db:
        db.execute("UPDATE files SET added_at=0")
    collect_garbage(ws)
    archive = backup(ws, tmp_path / "backups")
    restored = Workspace(restore(archive, tmp_path / "restored"))
    assert file_versions(restored, cid, upload["sha"])[0]["name"] == "source.pdf"
    assert restored.file_path(cid, upload["sha"]).read_bytes() == content


@pytest.mark.parametrize("key", ["sites", "contacts"])
def test_null_client_list_patch_is_rejected_and_legacy_null_is_readable(
    tmp_path: Path, key: str
) -> None:
    ws = Workspace(tmp_path / "workspace")
    client = create_client(ws, "Example", "12345678")
    cid = client["id"]
    http, headers = _session(ws)
    reply = http.patch(f"/clients/{cid}", headers=headers, json={"on_revision": 1, key: None})
    assert reply.status_code == 422
    assert get_client(ws, cid)["revision"] == 1
    with ws.connect() as db:
        db.execute("UPDATE clients SET sites_json='null',contacts_json='null' WHERE id=?", (cid,))
    assert http.get("/clients").status_code == 200
    assert http.get(f"/clients/{cid}").json()[key] == []
    assert http.get(f"/clients/{cid}/profile").json()["client"][key] == []


def _lookup(cui: str) -> tuple[str, bytes, dict]:
    company = {"date_generale": {"cui": cui, "denumire": "Example"}}
    return anaf.ANAF_URL, json.dumps({"found": [company]}).encode(), company


def test_cui_change_clears_anaf_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = Workspace(tmp_path / "workspace")
    client = create_client(ws, "Example", "12345678")
    monkeypatch.setattr(anaf, "_lookup", _lookup)
    anaf.refresh(ws, client["id"])
    assert profile(ws, client["id"])["identification"]["source"] == "anaf"
    update_client(ws, client["id"], {"cui": "87654321"}, 1)
    assert get_client(ws, client["id"])["anaf_refreshed_at"] is None
    assert profile(ws, client["id"])["identification"] is None


def test_pending_anaf_refresh_cannot_publish_after_client_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path / "workspace")
    client = create_client(ws, "Example", "12345678")
    entered, release = Event(), Event()
    errors: list[EmaError] = []

    def lookup(cui: str) -> tuple[str, bytes, dict]:
        entered.set()
        assert release.wait(5)
        return _lookup(cui)

    def refresh() -> None:
        try:
            anaf.refresh(ws, client["id"])
        except EmaError as exc:
            errors.append(exc)

    monkeypatch.setattr(anaf, "_lookup", lookup)
    thread = Thread(target=refresh)
    thread.start()
    try:
        assert entered.wait(5)
        update_client(ws, client["id"], {"cui": "87654321"}, 1)
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()
    assert [exc.code for exc in errors] == ["stale_revision"]
    assert profile(ws, client["id"])["identification"] is None
