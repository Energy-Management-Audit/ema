# S17b audit report OpenAPI diff

Generated contract: `openapi/ema.v1.json` via `uv run python scripts/generate_openapi_s16.py`.
Compared with `dev` @ b7706ad.

## Added

- `GET /jobs/{job_id}/audit/report` → `AuditReport` (404 `job_missing`, 400 `wrong_job_type`).
- Schema `AuditReport`: `draft: ReportRun | null`, `final: ReportRun | null`, `word: bool`.
- Schema `ReportRun`: `run_id`, `state`, `ended_at`, `current`, `summary: RenderSummary | null`,
  `docx_output_id`, `pdf_output_id`.
- Schema `RenderSummary`: `kind` (`draft|final`), `chapters: RenderChapter[]`, `tables`, `charts`,
  `markers: RenderMarker[]`, `fields_total`, `fields_confirmed`, `fields_manual` (all three over
  the fields found; `fields_manual` = entered by hand, no document source), `unit_plan: RenderUnitPlan`, `pdf`,
  `toc_pages_set`, `dropped: string[]`, `failures: RenderFailure[]`.
- Schemas `RenderChapter{number, title, section_id, page}`, `RenderMarker{section_id, label}`,
  `RenderFailure{section_id, code}`, `RenderUnitPlan{client_name, processes, processes_source
  (schemes|fisa|default), carriers, measured_panels, thermal_measurements, equipment_tables, measures}`.

## Changed

- `POST /jobs/{job_id}/stages/{stage}`: accepts `audit_render` (a draft, any readiness) and
  `audit_final` (`not_ready` 409 before `final_ok`, `word_unavailable` 424 without Word); 409 gains
  `audit_base_missing`, `audit_client_name`, `audit_package`, `audit_markers`,
  `audit_ai_wording` (fix round 1: the final's text mentions AI).
- Event `stage_failed` (not in the OpenAPI document): when a stage fails with a known refusal its
  payload is `{code, message}`; any other failure keeps `{code: "stage_failed"}`.

## Outputs of the two stages

`audit_render`: `Audit-ciorna.pdf` (when Word made it), then `Audit-ciorna.docx` (kind `draft`).
`audit_final`: `Audit-final.pdf`, then `Audit-final.docx` (kind `final`, saved last).
Artifact `render.json` of each run holds its `RenderSummary`.

## Fix round 1

- Readiness of an audit gains two blocking codes: `final_stale` (the newest final no longer matches
  its inputs: fields, section decisions, slots or the configured base files) and `ai_wording` (a
  narrative text mentions AI). `POST /stages/audit_final` ignores `final_stale`, since a new final
  is what replaces a stale one.
- `ReportRun.current` means the same thing: nothing the render read changed and it was made from
  the base files configured now.
