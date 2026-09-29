"""Client projections keep ANAF and annex sources separate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.unit.energy_data.test_annex_index import annex
from tests.workspace_jobs import create_job

from ema.clients import anaf
from ema.clients.overview import overview
from ema.clients.profile import profile
from ema.clients.registry import create_client, update_client
from ema.core.errors import EmaError
from ema.core.workspace import Workspace
from ema.energy_data.annex_index import import_annexes


def company(cui: int = 12345678) -> dict[str, object]:
    return {
        "date_generale": {
            "cui": cui,
            "denumire": "Exemplu din ANAF",
            "cod_CAEN": "5678",
            "adresa": "Strada Exemplu 2",
            "nrRegCom": "J00/1/2025",
        },
        "adresa_sediu_social": {"sdenumire_Judet": "Exemplu"},
        "stare_inactiv": {"statusInactivi": False},
        "inregistrare_scop_Tva": {"scpTVA": True},
    }


def test_overview_profile_source_order_and_memory(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    client = create_client(ws, "Client local", "RO12345678")
    path = tmp_path / "annex.xlsx"
    annex(path, name="Nume din anexă")
    with path.open("rb") as stream:
        imported = import_annexes(ws, [(path.name, stream)])
    assert imported.imported[0].client_id == client["id"]
    before = profile(ws, str(client["id"]))
    assert before["identification"]["source"] == "annex"
    assert before["contact_person"] is None
    assert overview(ws)[0]["consumption"] == {"year": 2025, "total_tep": "12.5"}
    assert overview(ws)[0]["annex_years"] == [2025]
    job = create_job(ws, "invoices", str(client["id"]), 2025)
    with ws.connect() as db:
        db.execute(
            "INSERT INTO decisions(id,job_id,field_id,at,data) VALUES (?,?,?,?,?)",
            ("decision-one", job, "identity", "2025-01-01T00:00:00Z", "{}"),
        )
        db.execute(
            "INSERT INTO client_memory(kind,identifier,legal_name,tax_id,job_id,decision_id) "
            "VALUES (?,?,?,?,?,?)",
            ("pod", "POD-EXEMPLU", "Client local", "12345678", job, "decision-one"),
        )
        db.execute(
            "INSERT INTO anaf_snapshots(client_id,status,retrieved_at,source_url,payload_json,sha) "
            "VALUES (?,?,?,?,?,?)",
            (
                client["id"],
                "complete",
                "2025-02-01T00:00:00Z",
                "https://example.test",
                json.dumps({"found": [company()]}),
                "sha",
            ),
        )
        db.execute(
            "UPDATE clients SET anaf_refreshed_at=? WHERE id=?",
            ("2025-02-01T00:00:00Z", client["id"]),
        )
    updated = update_client(
        ws,
        str(client["id"]),
        {
            "contacts": [
                {"id": "manager", "name": "Manager Exemplu", "role": "energy_manager"},
                {"id": "contact", "name": "Contact Exemplu", "role": "contact"},
            ]
        },
        int(client["revision"]),
    )
    assert updated["revision"] == 2
    view = profile(ws, str(client["id"]))
    assert view["identification"]["source"] == "anaf"
    assert view["fiscal"] == {"active": True, "vat_payer": True}
    assert view["energy_manager"]["name"] == "Manager Exemplu"
    assert view["contact_person"] == {
        "name": "Contact Exemplu",
        "source": "client",
        "annex_year": None,
    }
    listing = overview(ws)[0]
    assert listing["county"] == "Exemplu"
    assert listing["pods"] == ["POD-EXEMPLU"]
    with ws.connect() as db:
        db.execute(
            "UPDATE decisions SET data=? WHERE id=?", ('{"undone_by":"undo"}', "decision-one")
        )
    assert profile(ws, str(client["id"]))["memory"][0]["active"] is False
    assert overview(ws)[0]["pods"] == []


def test_anaf_create_validation_and_lookup_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path / "workspace")
    body = json.dumps({"found": [company()]}).encode()
    monkeypatch.setattr(
        anaf.web, "fetch_bytes", lambda *_args, **_kwargs: (anaf.ANAF_URL, "application/json", body)
    )
    created = anaf.create_from_anaf(ws, "RO 12345678")
    assert created["name"] == "Exemplu din ANAF"
    assert created["caen"] == "5678"
    with pytest.raises(EmaError) as duplicate:
        anaf.create_from_anaf(ws, "12345678")
    assert duplicate.value.code == "client_exists"
    with pytest.raises(EmaError) as invalid:
        anaf.create_from_anaf(ws, "X")
    assert invalid.value.code == "invalid_id"
    monkeypatch.setattr(
        anaf.web,
        "fetch_bytes",
        lambda *_args, **_kwargs: (anaf.ANAF_URL, "application/json", b'{"found":[]}'),
    )
    with pytest.raises(EmaError) as missing:
        anaf.create_from_anaf(ws, "87654321")
    assert missing.value.code == "anaf_missing"
    monkeypatch.setattr(
        anaf.web, "fetch_bytes", lambda *_args, **_kwargs: (anaf.ANAF_URL, "text/html", b"bad")
    )
    with pytest.raises(EmaError) as unavailable:
        anaf.create_from_anaf(ws, "87654321")
    assert unavailable.value.code == "anaf_unavailable"
    monkeypatch.setattr(
        anaf.web,
        "fetch_bytes",
        lambda *_args, **_kwargs: (
            anaf.ANAF_URL,
            "application/json",
            b'{"found":[{"date_generale":{"cui":87654321}}]}',
        ),
    )
    with pytest.raises(EmaError) as unnamed:
        anaf.create_from_anaf(ws, "87654321")
    assert unnamed.value.code == "anaf_unavailable"


def test_fiscal_missing_keys_remain_unknown(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    client = create_client(ws, "Exemplu", "12345678")
    with ws.connect() as db:
        db.execute(
            "INSERT INTO anaf_snapshots(client_id,status,retrieved_at,source_url,payload_json,sha) "
            "VALUES (?,?,?,?,?,?)",
            (
                client["id"],
                "complete",
                "2025-01-01",
                "https://example.test",
                json.dumps({"found": [{"date_generale": {"denumire": "Exemplu"}}]}),
                "sha",
            ),
        )
    assert profile(ws, str(client["id"]))["fiscal"] == {"active": None, "vat_payer": None}


def test_anaf_refresh_accepts_saved_cui_with_ro_and_spaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path / "workspace")
    client = create_client(ws, "Exemplu", "RO 12345678")
    payload = json.dumps({"found": [company()]}).encode()
    monkeypatch.setattr(
        anaf.web,
        "fetch_bytes",
        lambda *_args, **_kwargs: (anaf.ANAF_URL, "application/json", payload),
    )
    assert anaf.refresh(ws, str(client["id"]))["status"] == "complete"
