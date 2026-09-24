"""Provisional screen contracts and synthetic mock payloads."""

from __future__ import annotations

from typing import Any, cast

PROVISIONAL = [
    ("GET", "/clients"),
    ("POST", "/clients"),
    ("GET", "/clients/{client_id}"),
    ("PATCH", "/clients/{client_id}"),
    ("POST", "/clients/{client_id}/files"),
    ("GET", "/clients/{client_id}/files/{file_sha}/versions"),
    ("POST", "/clients/{client_id}/anaf/refresh"),
    ("GET", "/clients/{client_id}/sites"),
    ("GET", "/clients/{client_id}/contacts"),
    ("POST", "/jobs/{job_id}/stages/{stage}"),
    ("GET", "/jobs/{job_id}/facts"),
    ("PATCH", "/jobs/{job_id}/facts"),
    ("POST", "/jobs/{job_id}/conflicts/{conflict_id}"),
    ("PATCH", "/jobs/{job_id}/sections"),
    ("POST", "/jobs/{job_id}/sections/{section_id}/draft"),
    ("PATCH", "/jobs/{job_id}/deadline"),
    ("GET", "/jobs/{job_id}/preview.pdf"),
    ("GET", "/jobs/{job_id}/outputs"),
    ("GET", "/jobs/{job_id}/package"),
    ("POST", "/jobs/{job_id}/export/draft"),
    ("GET", "/jobs/{job_id}/measures"),
    ("GET", "/jobs/{job_id}/piee/data"),
    ("POST", "/jobs/{job_id}/piee/generate"),
    ("GET", "/jobs/{job_id}/prelucrare"),
    ("POST", "/jobs/{job_id}/prelucrare"),
    ("GET", "/jobs/{job_id}/invoices"),
    ("GET", "/jobs/{job_id}/invoices/identity"),
    ("POST", "/jobs/{job_id}/invoices/identity"),
    ("POST", "/jobs/{job_id}/invoices/{invoice_id}/anomaly"),
    ("POST", "/reporting/runs"),
    ("GET", "/reporting/runs/{run_id}"),
    ("GET", "/settings"),
    ("PUT", "/settings"),
    ("POST", "/settings/providers/{provider}/test"),
    ("GET", "/evidence/{evidence_id}/snippet.png"),
    ("GET", "/evidence/{evidence_id}/page.png"),
    ("POST", "/jobs/{job_id}/sections/{section_id}/na-proposal"),
]

_CLIENT = {
    "id": "client-exemplu",
    "name": "Societate Exemplu SRL",
    "cui": "00000000",
    "caen": "0000",
    "anaf_refreshed_at": "2026-01-01T00:00:00Z",
    "sites": [{"id": "site-exemplu", "name": "Sediu exemplu", "address": "Adresă sintetică"}],
    "contacts": [
        {"id": "contact-exemplu", "name": "Persoană exemplu", "role": "manager energetic"}
    ],
}
_IDENTITY = {
    "batch_id": "batch-exemplu",
    "candidate": {"client_id": "client-exemplu", "cui": "00000000", "pod": "POD-EXEMPLU"},
    "confirmed": False,
    "evidence_ids": ["evidence-exemplu"],
}
_SETTINGS = {
    "theme": "light",
    "default_provider": "gemini",
    "providers": {
        "gemini": {"present": False, "verified_at": None},
        "openai": {"present": False, "verified_at": None},
    },
    "extraction": {"ocr": True, "flag_uncertain": True, "auto_accept_exact": False},
}


def mock_example(method: str, path: str) -> Any:  # noqa: C901, PLR0911, PLR0912
    """Synthetic shapes only; no reference-library content enters the contract."""
    if path == "/clients":
        return [_CLIENT] if method == "GET" else _CLIENT
    if path == "/clients/{client_id}/sites":
        return _CLIENT["sites"]
    if path == "/clients/{client_id}/contacts":
        return _CLIENT["contacts"]
    if path.endswith("/files/{file_sha}/versions"):
        return [{"version": 1, "sha": "synthetic-sha", "name": "exemplu.pdf", "size_bytes": 4096}]
    if path.endswith("/files"):
        return {"sha": "synthetic-sha", "name": "exemplu.pdf", "intake": "reading"}
    if path.endswith("/anaf/refresh"):
        return {
            "client_id": "client-exemplu",
            "status": "complete",
            "retrieved_at": "2026-01-01T00:00:00Z",
            "source_url": "https://example.invalid/anaf",
        }
    if path.startswith("/clients"):
        return _CLIENT
    if path.endswith("/invoices/identity"):
        return _IDENTITY | {"confirmed": method == "POST"}
    if path.endswith("/invoices"):
        return {
            "batch_id": "batch-exemplu",
            "identity": _IDENTITY,
            "rows": [
                {
                    "id": "invoice-exemplu",
                    "month": "2026-01",
                    "consumption_kwh": 1200,
                    "source_evidence_ids": ["evidence-exemplu"],
                    "anomalies": [],
                }
            ],
            "missing_months": ["2026-02"],
        }
    if path.endswith("/anomaly"):
        return {
            "invoice_id": "invoice-exemplu",
            "resolution": "keep_in_month",
            "decision_id": "decision-exemplu",
        }
    if path.endswith("/piee/data"):
        return {
            "years": [2023, 2024, 2025],
            "carriers": [
                {
                    "carrier": "electricity",
                    "annual_mwh": [100, 110, 120],
                    "evidence_ids": ["evidence-exemplu"],
                }
            ],
            "conflicts": [],
            "missing": [],
        }
    if path.endswith("/measures"):
        return [
            {
                "id": "measure-exemplu",
                "name": "Măsură exemplu",
                "origin": "anexa",
                "savings_mwh": 12,
                "evidence_ids": ["evidence-exemplu"],
                "missing": [],
            }
        ]
    if path.endswith("/prelucrare"):
        return {
            "input": {"file_id": "file-exemplu", "years": [2023, 2024]},
            "output": {"id": "output-exemplu", "version": 1},
            "authority": "input_for_covered_years",
        }
    if path.endswith("/piee/generate"):
        return {"run_id": "run-exemplu", "stage": "draft", "status": "queued"}
    if path.endswith("/export/draft"):
        return {"run_id": "run-exemplu", "kind": "draft", "output_id": "output-exemplu"}
    if path.startswith("/reporting"):
        return {
            "id": "run-exemplu",
            "years": [2023, 2024, 2025],
            "client_ids": ["client-exemplu"],
            "exceptions": [],
            "output_id": "output-exemplu",
        }
    if path == "/settings":
        return _SETTINGS
    if path.startswith("/settings"):
        return {"provider": "gemini", "verified_at": "2026-01-01T00:00:00Z", "ok": True}
    if path.endswith("/na-proposal"):
        return {
            "section_id": "ch5.electric",
            "proposed_status": "n/a",
            "reason": "fără date aplicabile",
            "requires_human": True,
        }
    if path.endswith("/facts"):
        fact = {
            "id": "fact-exemplu",
            "key": "consum_anual",
            "value": 120,
            "evidence_ids": ["evidence-exemplu"],
        }
        return [fact] if method == "GET" else fact
    if "/conflicts/" in path:
        return {"decision_id": "decision-exemplu", "chosen": "candidate-exemplu", "revision": 2}
    if path.endswith("/sections"):
        return [{"id": "ch1", "status": "ready", "revision": 2}]
    if path.endswith("/deadline"):
        return {"deadline": "2026-12-31", "revision": 2}
    if path.endswith("/draft") or "/stages/" in path:
        return {
            "run_id": "run-exemplu",
            "stage": "draft",
            "state": "running",
            "done": 1,
            "total": 7,
        }
    if path.endswith("/outputs"):
        return [{"id": "output-exemplu", "version": 1, "kind": "draft", "edited_externally": False}]
    if path.endswith("/package"):
        return {
            "files": [{"id": "output-exemplu", "name": "exemplu.docx", "size_bytes": 4096}],
            "checks": [{"code": "sources", "ok": True, "detail": "Surse verificate"}],
        }
    return {"status": "pending"}


def request_example(method: str, path: str) -> Any:  # noqa: C901, PLR0911, PLR0912
    if method == "GET":
        return None
    if path == "/clients":
        return {"name": "Societate Exemplu SRL", "cui": "00000000"}
    if path == "/clients/{client_id}":
        return {"name": "Societate Exemplu SRL", "caen": "0000"}
    if path.endswith("/files"):
        return None
    if path.endswith("/invoices/identity"):
        return {"client_id": "client-exemplu", "on_revision": 1, "confirm": True}
    if path.endswith("/anomaly"):
        return {"resolution": "keep_in_month", "on_revision": 1}
    if path.endswith("/piee/generate"):
        return {"kind": "draft", "on_revision": 1}
    if path.endswith("/export/draft"):
        return {"on_revision": 1}
    if path.endswith("/prelucrare"):
        return {"file_id": "file-exemplu", "role": "input"}
    if path == "/reporting/runs":
        return {"years": [2023, 2024, 2025], "client_ids": ["client-exemplu"]}
    if path == "/settings":
        return {"theme": "dark"}
    if path.endswith("/na-proposal"):
        return {"reason": "fără date aplicabile", "on_revision": 1}
    if path.endswith("/facts"):
        return {"fact_id": "fact-exemplu", "value": 120, "on_revision": 1}
    if "/conflicts/" in path:
        return {"candidate_id": "candidate-exemplu", "on_revision": 1}
    if path.endswith("/sections"):
        return {"section_id": "ch1", "status": "ready", "on_revision": 1}
    if path.endswith("/deadline"):
        return {"deadline": "2026-12-31", "on_revision": 1}
    if path.endswith("/draft") or "/stages/" in path:
        return {"on_revision": 1}
    return {}


def request_body(method: str, path: str) -> dict[str, Any] | None:
    if method == "GET":
        return None
    if path.endswith("/files"):
        return {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {"file": {"type": "string", "format": "binary"}},
                        "required": ["file"],
                    }
                }
            },
        }
    request = request_example(method, path)
    return (
        {
            "required": True,
            "content": {
                "application/json": {"schema": example_schema(request), "example": request}
            },
        }
        if request is not None
        else None
    )


def example_schema(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        mapping = cast(dict[str, Any], value)
        return {
            "type": "object",
            "properties": {key: example_schema(item) for key, item in mapping.items()},
            "required": list(mapping),
        }
    if isinstance(value, list):
        items = cast(list[Any], value)
        return {"type": "array", "items": example_schema(items[0]) if items else {}}
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    return {"type": "string"}
