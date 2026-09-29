"""Stable problem responses at the HTTP trust boundary."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from ema.api.error_status import STATUS
from ema.core.errors import EmaError

ROUTE_ERRORS: dict[tuple[str, str], tuple[str, ...]] = {
    ("POST", "/jobs/{job_id}/log/{decision_id}/undo"): (
        "decision_missing",
        "already_undone",
        "decision_superseded",
        "field_changed",
        "field_missing",
        "section_missing",
        "transition_forbidden",
        "stale_revision",
    ),
    ("POST", "/jobs/{job_id}/fields/{field_id}/decide"): (
        "field_missing",
        "stale_revision",
        "value_missing",
        "value_invalid",
        "alternative_missing",
        "field_unresolved",
        "action_invalid",
    ),
    ("PATCH", "/jobs/{job_id}/sections/{section_id}"): (
        "job_missing",
        "wrong_job_type",
        "section_missing",
        "stale_revision",
        "transition_forbidden",
        "human_required",
        "reason_missing",
    ),
    ("DELETE", "/jobs/{job_id}/slots/{slot}/versions/{version}"): (
        "job_missing",
        "slot_missing",
        "version_missing",
        "stale_revision",
        "human_required",
    ),
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
        "sections_stale",
    ),
    ("POST", "/jobs/{job_id}/sections/{section_id}/draft"): ("provisional_contract",),
    ("GET", "/jobs/{job_id}/outputs"): ("job_missing",),
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
    ("GET", "/jobs/{job_id}/invoices"): ("job_missing", "wrong_job_type", "invoices_missing"),
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
    ("PUT", "/settings"): ("key_not_allowed", "backup_dir_invalid"),
    ("POST", "/settings/providers/{provider}/test"): ("provider_invalid",),
    # s17b-home-settings
    ("PUT", "/settings/providers/{provider}/key"): ("provider_invalid", "keyring_unavailable"),
    ("DELETE", "/settings/providers/{provider}/key"): ("provider_invalid", "keyring_unavailable"),
    ("POST", "/backups"): (
        "backup_dir_missing",
        "backup_dir_invalid",
        "backup_changed",
        "backup_failed",
    ),
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
    ("POST", "/jobs/{job_id}/export"): (
        "human_required",
        "hash_mismatch",
        "stale_revision",
        "job_running",
        "not_ready",
        "output_stale",
        "output_missing",
        "output_not_final",
        "output_copy_failed",
        "output_changed",
        "file_missing",
        "output_path",
    ),
    ("GET", "/jobs/{job_id}/outputs/{output_id}"): (
        "job_missing",
        "output_missing",
        "file_type",
    ),
    # s17b-audit-report
    ("GET", "/jobs/{job_id}/audit/report"): ("job_missing", "wrong_job_type"),
    # s17b-audit-work
    ("GET", "/jobs/{job_id}/audit/documents"): ("job_missing", "wrong_job_type"),
    ("GET", "/jobs/{job_id}/audit/outline"): ("job_missing", "wrong_job_type"),
    ("PUT", "/jobs/{job_id}/audit/notes/{section_id}"): (
        "job_missing",
        "wrong_job_type",
        "section_missing",
        "stale_revision",
    ),
    ("PUT", "/jobs/{job_id}/audit/deadline"): ("job_missing", "wrong_job_type", "stale_revision"),
    # s17b-clients-reporting
    ("POST", "/clients"): ("client_exists", "invalid_id"),
    ("GET", "/clients/overview"): (),
    ("POST", "/clients/annexes"): ("file_too_large",),
    ("POST", "/clients/from-anaf"): (
        "invalid_id",
        "client_exists",
        "anaf_missing",
        "anaf_unavailable",
    ),
    ("GET", "/clients/{client_id}/profile"): ("client_missing", "invalid_id"),
    ("GET", "/reporting/runs"): (),
    ("POST", "/reporting/runs"): ("invalid_year", "invalid_id", "client_missing"),
    ("GET", "/reporting/runs/{run_id}"): ("run_missing",),
    ("GET", "/reporting/runs/{run_id}/preview"): ("run_missing", "run_not_ready"),
    # s17b-invoices
    ("POST", "/jobs/{job_id}/invoices/files"): (
        "job_missing",
        "wrong_job_type",
        "invalid_slot",
        "job_running",
        "validation_error",
    ),
    ("GET", "/jobs/{job_id}/invoices/page.png"): (
        "job_missing",
        "wrong_job_type",
        "invalid_slot",
        "file_missing",
        "evidence_missing",
        "file_type",
    ),
    ("GET", "/jobs/{job_id}/invoices/file"): (
        "job_missing",
        "wrong_job_type",
        "invalid_slot",
        "file_missing",
        "file_type",
    ),
}
# s17b-audit-report
ROUTE_ERRORS[("POST", "/jobs/{job_id}/stages/{stage}")] += (
    "audit_base_missing",
    "audit_client_name",
    "audit_package",
    "audit_markers",
    "audit_ai_wording",
)

# s17b-audit-final: only an audit's cover photo is checked for its type when it is set.
ROUTE_ERRORS[("PUT", "/jobs/{job_id}/slots/{slot:path}")] = (
    "job_missing",
    "invalid_slot",
    "file_missing",
    "cover_photo_type",
)

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
