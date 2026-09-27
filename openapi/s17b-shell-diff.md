# S17b shell OpenAPI diff

Generated contract: `openapi/ema.v1.json` via `uv run python scripts/generate_openapi_s16.py`.
Compared with `dev` before this slice.

## Added

- `GET /jobs/overview` → `JobOverview[]`
- Schema `JobOverview`: `id`, `type`, `client_slug`, `client_name`, `year`, `state`, `revision`, `created_at`, `updated_at`, `final_ok`, `blocking`, `next`, `readiness_error`, `approved_at`, `finalized`.

## Removed

- `PATCH /jobs/{job_id}/deadline`
- `POST /jobs/{job_id}/invoices/{invoice_id}/anomaly`
- `GET /jobs/{job_id}/package`
- `GET /jobs/{job_id}/preview.pdf`

`POST /jobs/{job_id}/sections/{section_id}/draft` remains provisional. The removed paths now answer 404 `not_found`.
