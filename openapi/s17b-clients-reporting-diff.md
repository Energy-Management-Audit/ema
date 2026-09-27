# S17b clients and reporting API diff

Generated contract: `openapi/ema.v1.json`; baseline: `openapi/ema.v1.s16a.json`.

| Operation | Response | Purpose |
|---|---|---|
| `GET /clients/overview` | `200 ClientOverview[]` | Client list with indexed annex years, consumption, county and POD memory. |
| `POST /clients/annexes` | `200 AnnexImport` | Multipart `files` import with per-file imported and ignored rows. |
| `POST /clients/from-anaf` | `201 Client` | ANAF lookup and client creation by CUI. |
| `GET /clients/{client_id}/profile` | `200 ClientProfile` | Source-labelled client identity, contacts, memory and annexes. |
| `GET /reporting/runs` | `200 ReportingRun[]` | Newest reporting runs first. |
| `GET /reporting/runs/{run_id}/preview` | `200 ReportingPreview` | Ready run's source-based row preview; `409 run_not_ready` otherwise. |

`ReportingRun` now includes `job_id` and `created_at`. Its exceptions include source name, beneficiary, decision and a spreadsheet cell reference when one is available. The generated `openapi/s16-diff.md` records these operations and all schema changes against the S16 baseline.
