# S17b audit final (A) OpenAPI diff

Generated contract: `openapi/ema.v1.json` via `uv run python scripts/generate_openapi_s16.py`.
Compared with `dev` @ dc642b8 (#52 and #53 merged); regenerated once, as the plan asks.

## Changed

- `PATCH /jobs/{job_id}/sections`: 409 gains `sections_stale` ("Unele secţiuni au ciorna veche.").
  Before any item is written, the request refreshes staleness (facts, materials, the configured
  audit base) in its own transaction and commits those marks; if an item asks for `done` on a
  stale section, the whole batch is refused and nothing of it is written. The problem body stays
  `{type, title, status}`: the refused ids are not in it. A client names them from the outline it
  reads again after the 409 (the marks are committed): the chapter's drafted nodes now `stale`.
- Schema `RenderSummary`: gains `charts_skipped: string[]` (default `[]`), the chart variants a
  render did not draw for want of her wording (filled by sub-slice B).

## Not in the OpenAPI document

- Stage `audit_final` fails with `base_changed` ("Baza raportului s-a schimbat. Refaceţi
  ciorna.") when the configured base changed after its sections were confirmed; the
  `stage_failed` payload is `{code, message}`.
- `audit_render` item failures gain `ch4_no_data` (no carrier or year in the dataset) and
  `draft_prototype` (the base lacks a section, or a prototype its content needs); `draft_slots`
  is gone.
- `POST /jobs/{job_id}/export`: a refusal for readiness (`not_ready`) now commits the staleness
  marks it made before answering, as the export use case already did.

## Fix round 2

- Readiness of an audit gains the blocking code `cover_photo_changed` ("Fotografia sediului s-a
  schimbat după ciornă. Refaceţi ciorna."): the newest draft showed another cover photo (or none)
  than the one in slot `cover/photo` now. `POST /stages/audit_final` refuses it (`not_ready`); a
  new draft clears it.
- `PUT /jobs/{job_id}/slots/{slot}` now declares its errors: 400 `invalid_slot`, 404
  `job_missing`/`file_missing`, and 415 `cover_photo_type` ("Fotografia sediului nu este JPEG sau
  PNG."), when the slot is `cover/photo` and the file is not a JPEG or PNG. The slot keeps its
  version.
- Stage `audit_final` fails with `audit_package` when a picture bullet of the numbering has no
  approved image digest (detail `unreviewed picture bullet: word/media/…`).
