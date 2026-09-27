# S17b audit work API diff

Generated snapshot: `openapi/ema.v1.json` via `uv run python scripts/generate_openapi_s16.py`.

| Operation | Response | Errors |
|---|---|---|
| `GET /jobs/{job_id}/audit/documents` | `AuditDocuments` | `job_missing`, `wrong_job_type` |
| `GET /jobs/{job_id}/audit/outline` | `AuditOutline` | `job_missing`, `wrong_job_type` |
| `PUT /jobs/{job_id}/audit/notes/{section_id}` | `AuditNoteResult` | `job_missing`, `wrong_job_type`, `section_missing`, `stale_revision`, `validation_error` |
| `PUT /jobs/{job_id}/audit/deadline` | `AuditDeadlineResult` | `job_missing`, `wrong_job_type`, `stale_revision`, `validation_error` |

The `DocFile` response binds an intake result to the active slot SHA and carries its displayed `slot_revision` for `Scoate`. Older intake artifacts without `file_sha` show `unread` until a new intake run. Anexa and Măsuri show `read` only when their respective current ready stage read that active slot revision.

The `AuditOutline.nodes` response includes `computed_status` (`missing`, `ready` or `drafted`) in the same snapshot as the displayed proposal. A user may reject `n/a proposed` with `PATCH /jobs/{job_id}/audit/sections/{section_id}` targeting that computed status; a stale target is rejected. `drafted` is now an accepted request status for this edge.

`GET /jobs/{job_id}/status` now returns typed `JobRun` rows with `started_at` and nullable `ended_at` so audit activity can display terminal run times. The existing run fields remain unchanged.

`GET /jobs/{job_id}/slots/{slot}/versions` adds `slot_revision` to each `SlotVersion`, allowing `Scoate` to send the exact revision it displayed. Upload validation also recognizes an HTML workbook saved with an `.xls` or `.xlsx` filename; other extension/content mismatches remain invalid.
