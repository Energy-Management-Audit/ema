"""Stable problem responses at the HTTP trust boundary."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from ema.core.errors import EmaError

STATUS = {
    "job_missing": 404,
    "client_missing": 404,
    "output_missing": 404,
    "evidence_missing": 404,
    "run_missing": 404,
    "file_missing": 404,
    "anaf_missing": 404,
    "field_missing": 404,
    "section_missing": 404,
    "stale_revision": 409,
    "job_running": 409,
    "not_ready": 409,
    "import_required": 409,
    "output_stale": 409,
    "output_not_final": 409,
    "conflict_open": 409,
    "client_exists": 409,
    "checklist_file": 409,
    "client_memory_conflict": 409,
    "invoices_missing": 409,
    "invoices_stale": 409,
    "invoices_unconfirmed_client": 409,
    "client_confirmed": 409,
    "piee_base_missing": 409,
    "piee_base_review_required": 409,
    "piee_base_changed": 409,
    "measures_form_missing": 409,
    "measures_form_invalid": 409,
    "word_unavailable": 424,
    "anaf_unavailable": 424,
    "audit_render_unavailable": 501,
    "provisional_contract": 501,
    "file_too_large": 413,
    "file_type": 415,
    "evidence_not_pdf": 415,
    "invalid_id": 400,
    "invalid_slot": 400,
    "invalid_stage": 400,
    "invalid_year": 400,
    "invalid_cursor": 400,
    "key_not_allowed": 400,
    "wrong_job_type": 400,
    "provider_invalid": 400,
    "human_required": 403,
    "ai_client_disabled": 403,
    "model_no_vision": 409,
    "confirmation_individual": 409,
    "visit_missing": 409,
    "hash_mismatch": 403,
}

ROUTE_ERRORS: dict[tuple[str, str], tuple[str, ...]] = {
    ("POST", "/clients"): ("client_exists", "invalid_id"),
    ("GET", "/clients/{client_id}"): ("client_missing",),
    ("PATCH", "/clients/{client_id}"): ("client_missing", "stale_revision"),
    ("POST", "/clients/{client_id}/files"): (
        "client_missing",
        "file_too_large",
        "file_type",
    ),
    ("GET", "/clients/{client_id}/files/{file_sha}/versions"): (
        "client_missing",
        "file_missing",
    ),
    ("POST", "/clients/{client_id}/anaf/refresh"): (
        "client_missing",
        "anaf_unavailable",
        "anaf_missing",
    ),
    ("GET", "/clients/{client_id}/sites"): ("client_missing",),
    ("GET", "/clients/{client_id}/contacts"): ("client_missing",),
    ("POST", "/jobs/{job_id}/stages/{stage}"): (
        "job_missing",
        "invalid_stage",
        "stale_revision",
        "job_running",
        "not_ready",
        "word_unavailable",
        "provisional_contract",
        "human_required",
        "import_required",
        "wrong_job_type",
        "invalid_year",
        "file_type",
        "piee_base_missing",
        "piee_base_review_required",
        "piee_base_changed",
        "ai_client_disabled",
        "visit_missing",
        "measures_form_missing",
        "measures_form_invalid",
    ),
    ("POST", "/jobs/{job_id}/conflicts/{conflict_id}"): (
        "job_missing",
        "field_missing",
        "stale_revision",
        "conflict_open",
    ),
    ("PATCH", "/jobs/{job_id}/sections"): (
        "job_missing",
        "section_missing",
        "human_required",
        "stale_revision",
    ),
    ("POST", "/jobs/{job_id}/sections/{section_id}/draft"): ("provisional_contract",),
    ("PATCH", "/jobs/{job_id}/deadline"): ("provisional_contract",),
    ("GET", "/jobs/{job_id}/preview.pdf"): ("provisional_contract", "output_missing"),
    ("GET", "/jobs/{job_id}/outputs"): ("job_missing",),
    ("GET", "/jobs/{job_id}/package"): ("provisional_contract",),
    ("POST", "/jobs/{job_id}/export/draft"): (
        "audit_render_unavailable",
        "job_missing",
        "stale_revision",
        "invoices_unconfirmed_client",
    ),
    ("GET", "/jobs/{job_id}/measures"): ("job_missing", "wrong_job_type"),
    ("GET", "/jobs/{job_id}/visit"): ("job_missing", "wrong_job_type"),
    ("POST", "/jobs/{job_id}/fields/accept-batch"): (
        "confirmation_individual",
        "human_required",
        "stale_revision",
    ),
    ("GET", "/jobs/{job_id}/piee/data"): ("job_missing", "wrong_job_type"),
    ("GET", "/jobs/{job_id}/piee/summary"): ("job_missing", "wrong_job_type"),
    ("GET", "/jobs/{job_id}/approvals"): ("job_missing",),
    ("POST", "/jobs/{job_id}/piee/import"): (
        "job_missing",
        "wrong_job_type",
        "invalid_year",
        "stale_revision",
        "job_running",
        "not_ready",
        "file_type",
    ),
    ("POST", "/jobs/{job_id}/piee/generate"): (
        "job_missing",
        "stale_revision",
        "job_running",
        "wrong_job_type",
        "invalid_year",
        "not_ready",
        "import_required",
        "piee_base_missing",
        "piee_base_review_required",
        "piee_base_changed",
    ),
    ("GET", "/jobs/{job_id}/prelucrare"): ("job_missing", "wrong_job_type"),
    ("POST", "/jobs/{job_id}/prelucrare"): (
        "job_missing",
        "file_missing",
        "file_type",
        "job_running",
    ),
    ("GET", "/jobs/{job_id}/invoices"): ("job_missing", "wrong_job_type"),
    ("GET", "/jobs/{job_id}/invoices/identity"): (
        "job_missing",
        "invoices_missing",
    ),
    ("POST", "/jobs/{job_id}/invoices/identity"): (
        "human_required",
        "job_missing",
        "stale_revision",
        "client_memory_conflict",
    ),
    ("POST", "/jobs/{job_id}/invoices/{invoice_id}/anomaly"): ("provisional_contract",),
    ("POST", "/reporting/runs"): ("invalid_year", "client_missing", "job_running"),
    ("GET", "/reporting/runs/{run_id}"): ("run_missing",),
    ("PUT", "/settings"): ("key_not_allowed",),
    ("POST", "/settings/providers/{provider}/test"): ("provider_invalid",),
    ("GET", "/evidence/{evidence_id}/snippet.png"): (
        "evidence_missing",
        "file_missing",
        "evidence_not_pdf",
    ),
    ("GET", "/evidence/{evidence_id}/page.png"): (
        "evidence_missing",
        "file_missing",
        "evidence_not_pdf",
    ),
    ("POST", "/jobs/{job_id}/sections/{section_id}/na-proposal"): (
        "job_missing",
        "section_missing",
        "stale_revision",
    ),
    ("POST", "/jobs/{job_id}/export"): (
        "human_required",
        "hash_mismatch",
        "stale_revision",
        "job_running",
        "not_ready",
        "output_stale",
        "output_missing",
        "output_not_final",
    ),
    ("GET", "/jobs/{job_id}/outputs/{output_id}"): (
        "job_missing",
        "output_missing",
        "file_type",
    ),
}

_PROBLEM_SCHEMA = {
    "type": "object",
    "required": ["type", "title", "status"],
    "properties": {
        "type": {"type": "string", "pattern": "^urn:ema:error:"},
        "title": {"type": "string"},
        "status": {"type": "integer"},
    },
}


def install_error_contract(app: FastAPI) -> None:
    """Expose exact runtime problem media and route-specific status codes."""
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        method = next(iter(route.methods or {"GET"}))
        codes = ["invalid_host", "invalid_origin"]
        if route.path not in {"/session", "/health"}:
            codes.append("session_required")
            if method not in {"GET", "HEAD", "OPTIONS"}:
                codes.append("csrf_required")
        if route.path == "/session":
            codes.append("session_required")
        codes.extend(ROUTE_ERRORS.get((method, route.path), ()))
        by_status: dict[int, list[str]] = {}
        for code in codes:
            status = (
                421
                if code == "invalid_host"
                else 403
                if code in {"invalid_origin", "session_required", "csrf_required"}
                else STATUS[code]
            )
            by_status.setdefault(status, []).append(code)
        by_status[422] = ["validation_error"]
        for status, names in by_status.items():
            route.responses[status] = {
                "description": ", ".join(sorted(set(names))),
                "content": {
                    "application/problem+json": {
                        "schema": _PROBLEM_SCHEMA,
                    }
                },
            }


TITLES = {
    "invalid_host": "Gazda cererii este invalidă.",
    "invalid_origin": "Originea cererii este invalidă.",
    "session_required": "Sesiunea este necesară.",
    "csrf_required": "Confirmarea sesiunii este necesară.",
    "human_required": "Confirmarea umană este necesară.",
    "hash_mismatch": "Versiunea de pregătire nu corespunde.",
    "provisional_contract": "Această funcţie nu este încă disponibilă.",
}


def problem(code: str, status: int | None = None, title: str | None = None) -> JSONResponse:
    actual = status or STATUS.get(code, 400)
    return JSONResponse(
        {
            "type": f"urn:ema:error:{code}",
            "title": title or TITLES.get(code, "Cererea nu poate fi procesată."),
            "status": actual,
        },
        status_code=actual,
        media_type="application/problem+json",
    )


def from_ema(error: EmaError) -> JSONResponse:
    return problem(error.code, title=error.user_message_ro)
