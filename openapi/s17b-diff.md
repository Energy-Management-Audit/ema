# S17b contract diff (PIEE journey)

Additive to `ema.v1.json` as of S16. Regenerate with `uv run python scripts/generate_openapi_s16.py`.

## Added operations

- `POST /jobs/{job_id}/piee/import`: body `PieeImport {on_revision}`, returns **202**
  `RunStart {run_id, stage: "piee_import", state: "running"}`. Errors: `job_missing`,
  `wrong_job_type`, `invalid_year`, `stale_revision`, `job_running`, `not_ready` (no Anexa),
  `file_type`. `POST /jobs/{job_id}/stages/piee_import` dispatches the same use case (B1).
- `GET /jobs/{job_id}/piee/summary`: returns `PieeSummary` (`total_tep`, `annual_check`,
  `savings_mwh`, `investment_thousand_lei` as `SummaryFigure {value, unit, field_ids, missing}`,
  plus `measures_total`, `measures_complete`, `measures_without_term`). Errors: `job_missing`,
  `wrong_job_type` (B4).
- `GET /jobs/{job_id}/approvals`: returns `Approval[]`
  (`id, job_id, output_id, readiness_hash, on_decision, at, actor`), newest first. Error:
  `job_missing` (B6).

## Changed schemas

- `Output` gains `name` (stored name without the run prefix), `created_at` (the run's
  `ended_at`), `run_id` and `stage` (B5).

## Changed behaviour

- `GET /jobs/{job_id}/export/checks` answers 200 with the `draft_missing` issue before a first
  draft, instead of `400 piee_output_missing` (B7).
- PIEE readiness adds the blocking issue `import_required` (`Documentele trebuie citite din nou.`)
  when there is no current import run.
- PIEE readiness adds the blocking issue `months_annual_mismatch`
  (`Suma lunilor nu se potriveşte cu totalul anual.`, `field_id` = the annual `carrier.<c>.<y>`
  field) for each carrier and year whose 12 months, as reviewed, differ from the filed annual
  reading by more than half a unit of every figure's written precision. Correcting the annual
  value (or the months) clears it; the final export stays `409 not_ready` meanwhile.
- `GET /jobs/{job_id}/measures` fills `savings_mwh` from the `saving_mwh` fields (B8).

## New problem code

- `import_required`, **409**, `Documentele trebuie citite din nou.`: on
  `POST /jobs/{job_id}/piee/generate` and `POST /jobs/{job_id}/stages/{stage}` when the documents
  were never read or a slot changed since the last import (B2).

## New readiness issue code

- `months_annual_mismatch` (see Changed behaviour). It is a `Readiness.blocking[].code`, not an
  HTTP problem; `Issue.code` stays a free string in the schema.

## Outside the schema

- `GET /app` and `GET /app/{path}` serve the built `index.html` without a session
  (`include_in_schema=False`); `ema serve` prints `{origin}/app/#code={code}`.
