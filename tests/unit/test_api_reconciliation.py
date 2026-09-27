"""S16 operation inventory and provisional boundaries."""

import inspect
import json
import re
from pathlib import Path
from typing import Literal, get_args, get_origin

from fastapi.testclient import TestClient
from pydantic import BaseModel

from ema.api import create_app
from ema.api import models as wire_models
from ema.api.provisional import REASONS
from ema.core.jobs import create_job
from ema.core.workspace import Workspace

BASE = "http://127.0.0.1:8766"


def _operations(schema: dict) -> dict[tuple[str, str], dict]:
    return {
        (method.upper(), path): details
        for path, methods in schema["paths"].items()
        for method, details in methods.items()
        if method in {"get", "post", "put", "patch", "delete"}
    }


def test_inventory_and_generated_contract(tmp_path: Path) -> None:
    schema = create_app(Workspace(tmp_path), 8766).openapi()
    committed = json.loads(Path("openapi/ema.v1.json").read_text(encoding="utf-8"))
    assert schema == committed
    baseline = json.loads(Path("openapi/ema.v1.s16a.json").read_text(encoding="utf-8"))
    old, new = _operations(baseline), _operations(schema)
    old_provisional = {key for key, operation in old.items() if operation.get("x-provisional")}
    new_provisional = {key for key, operation in new.items() if operation.get("x-provisional")}
    assert len(old_provisional) == 37
    assert new_provisional == {
        (method, path) for method, path in (("POST", "/jobs/{job_id}/sections/{section_id}/draft"),)
    }
    assert all(new[key]["x-provisional"] == REASONS[key[1]] for key in new_provisional)
    assert len(old_provisional - new_provisional - (old.keys() - new.keys())) == 30
    assert old.keys() - new.keys() == {
        ("GET", "/jobs/{job_id}/facts"),
        ("PATCH", "/jobs/{job_id}/facts"),
        ("PATCH", "/jobs/{job_id}/deadline"),
        ("GET", "/jobs/{job_id}/preview.pdf"),
        ("GET", "/jobs/{job_id}/package"),
        ("POST", "/jobs/{job_id}/invoices/{invoice_id}/anomaly"),
    }
    # S17b adds the PIEE import, its summary and the approvals read (openapi/s17b-diff.md).
    assert new.keys() - old.keys() == {
        ("GET", "/jobs/overview"),
        ("GET", "/audit/forms/masuri-propuse.xlsx"),
        ("POST", "/jobs/{job_id}/piee/import"),
        ("GET", "/jobs/{job_id}/piee/summary"),
        ("GET", "/jobs/{job_id}/approvals"),
        ("GET", "/jobs/{job_id}/visit"),
        ("GET", "/jobs/{job_id}/audit/documents"),  # s17b-audit-work
        ("GET", "/jobs/{job_id}/audit/outline"),  # s17b-audit-work
        ("PUT", "/jobs/{job_id}/audit/notes/{section_id}"),  # s17b-audit-work
        ("PUT", "/jobs/{job_id}/audit/deadline"),  # s17b-audit-work
        ("GET", "/clients/overview"),  # s17b-clients-reporting
        ("POST", "/clients/annexes"),  # s17b-clients-reporting
        ("POST", "/clients/from-anaf"),  # s17b-clients-reporting
        ("GET", "/clients/{client_id}/profile"),  # s17b-clients-reporting
        ("GET", "/reporting/runs"),  # s17b-clients-reporting
        ("GET", "/reporting/runs/{run_id}/preview"),  # s17b-clients-reporting
        ("PUT", "/settings/providers/{provider}/key"),  # s17b-home-settings
        ("DELETE", "/settings/providers/{provider}/key"),  # s17b-home-settings
        ("POST", "/backups"),  # s17b-home-settings
        ("GET", "/settings/update"),  # s18-update
        ("GET", "/jobs/{job_id}/audit/report"),  # s17b-audit-report
        ("POST", "/jobs/{job_id}/invoices/files"),  # s17b-invoices
        ("GET", "/jobs/{job_id}/invoices/page.png"),  # s17b-invoices
        ("GET", "/jobs/{job_id}/invoices/file"),  # s17b-invoices
    }
    diff = Path("openapi/s16-diff.md").read_text(encoding="utf-8")
    added_text = diff.split("### Added\n", 1)[1].split("### Removed\n", 1)[0]
    removed_text = diff.split("### Removed\n", 1)[1].split("## Changed operations", 1)[0]
    listed_added = set(re.findall(r"- `(GET|POST|PUT|PATCH|DELETE) ([^`]+)`", added_text))
    listed_removed = set(re.findall(r"- `(GET|POST|PUT|PATCH|DELETE) ([^`]+)`", removed_text))
    assert listed_added == new.keys() - old.keys()
    assert listed_removed == old.keys() - new.keys()
    changed_text = diff.split("## Changed operations\n", 1)[1].split("## Schemas", 1)[0]
    listed_changed = set(re.findall(r"\| `(GET|POST|PUT|PATCH|DELETE) ([^`]+)`", changed_text))
    assert listed_changed == {key for key in old.keys() & new.keys() if old[key] != new[key]}
    for method, path in old.keys() - new.keys():
        assert f"`{method} {path}`" in diff
    stage = new[("POST", "/jobs/{job_id}/stages/{stage}")]
    assert "x-provisional" not in stage
    assert "fill and draft return 501" in stage["description"]
    binary = new[("GET", "/jobs/{job_id}/outputs/{output_id}")]["responses"]["200"]["content"]
    assert set(binary) == {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    assert "`Job`: `revision`" in diff
    assert "`JobStatus`: `revision`" in diff
    client_errors = new[("POST", "/clients")]["responses"]
    assert set(client_errors["403"]["content"]) == {"application/problem+json"}
    assert "client_exists" in client_errors["409"]["description"]


def test_removed_provisional_paths_answer_not_found(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    job = create_job(ws, "audit", "synthetic", 2026)
    client = TestClient(create_app(ws, 8766, launch_code="synthetic-code"), base_url=BASE)
    token = client.post("/session", json={"code": "synthetic-code"}).json()["csrf"]
    for method, path in (
        ("PATCH", f"/jobs/{job}/deadline"),
        ("POST", f"/jobs/{job}/invoices/invoice-1/anomaly"),
        ("GET", f"/jobs/{job}/package"),
        ("GET", f"/jobs/{job}/preview.pdf"),
    ):
        response = client.request(method, path, headers={"x-ema-csrf": token})
        assert response.status_code == 404
        assert response.json()["type"] == "urn:ema:error:not_found"


def test_unavailable_audit_agents_create_no_run_or_event(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    job = create_job(ws, "audit", "synthetic", 2026)
    app = create_app(ws, 8766, launch_code="synthetic-code")
    client = TestClient(app, base_url=BASE)
    token = client.post("/session", json={"code": "synthetic-code"}).json()["csrf"]
    headers = {"X-Ema-CSRF": token}
    with ws.connect() as db:
        revision = db.execute("SELECT revision FROM jobs WHERE id=?", (job,)).fetchone()[0]
    for stage in ("fill", "draft"):
        response = client.post(
            f"/jobs/{job}/stages/{stage}", json={"on_revision": revision}, headers=headers
        )
        assert response.status_code == 501
        assert response.json()["type"] == "urn:ema:error:provisional_contract"
    draft = client.post(
        f"/jobs/{job}/export/draft", json={"on_revision": revision}, headers=headers
    )
    assert draft.status_code == 501
    assert draft.json()["type"] == "urn:ema:error:audit_render_unavailable"
    with ws.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM runs WHERE job_id=?", (job,)).fetchone()[0] == 0
        assert (
            db.execute("SELECT COUNT(*) FROM job_events WHERE job_id=?", (job,)).fetchone()[0] == 0
        )


def test_wire_optional_and_literal_schema(tmp_path: Path) -> None:
    schemas = create_app(Workspace(tmp_path), 8766).openapi()["components"]["schemas"]
    for name, model in inspect.getmembers(wire_models, inspect.isclass):
        if not issubclass(model, BaseModel) or model.__module__ != wire_models.__name__:
            continue
        schema = schemas[name]
        for field_name, field in model.model_fields.items():
            property_schema = schema["properties"][field_name]
            parts = get_args(field.annotation)
            if type(None) in parts:
                assert {"type": "null"} in property_schema.get("anyOf", []), (name, field_name)
                if not field.is_required():
                    assert field_name not in schema.get("required", []), (name, field_name)
            literal = (
                field.annotation
                if get_origin(field.annotation) is Literal
                else next((part for part in parts if get_origin(part) is Literal), None)
            )
            if literal is not None:
                values = set(get_args(literal))
                choices = property_schema.get("anyOf", [property_schema])
                actual = {choice["const"] for choice in choices if "const" in choice} | {
                    value for choice in choices for value in choice.get("enum", [])
                }
                assert actual == values, (name, field_name)
