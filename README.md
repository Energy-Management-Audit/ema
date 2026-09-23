# Ema

Ema prepares the recurring paperwork of **Energy Management & Audit SRL**: electricity invoices,
the yearly PIEE, energy audits, and the energy-manager report. The deliverables are Word and Excel
documents in the auditor's own format, and every number in them is traceable to the document it
came from.

One Python package in one process: FastAPI serves the API and the built frontend, pywebview shows
it in a native Windows window, and the same use cases run headless from the CLI.

## Status

The core workspace, job store, backup, CLI and health API are available. Other workflows arrive
slice by slice under `docs/PLAN.md` §7.

## Getting started

```bash
uv sync --all-groups        # Python 3.12 toolchain and dependencies
uv run pre-commit install --install-hooks -t pre-commit -t pre-push
scripts/check              # non-mutating gate, same command as CI and pre-push
```

Golden tests read the real reference library, which lives outside this repository and never enters
git. To run them:

```bash
export EMA_REFERENCE=~/Code/projects/ema-reference
uv run pytest -m golden
```

## Layout

| Path | Holds |
|---|---|
| `src/ema/core/` | workspace, jobs, office documents, pdf/ocr, llm, web, config, logging, errors |
| `src/ema/clients/` · `energy_data/` · `consumption_analysis/` | the shared domain |
| `src/ema/invoices/` · `piee/` · `audit/` · `reporting/` | one workflow each, never importing each other |
| `src/ema/api/` · `cli/` · `mcp/` | interfaces, no business logic |
| `templates/` | the auditor's documents used as templates |
| `frontend/` | React + TypeScript, built into the package |
| `packaging/` | the Windows build (see `docs/decisions/0001-packaging-and-resources.md`) |
| `docs/PLAN.md` | the plan and design of record |

## Working here

Read `AGENTS.md` first: it is the one page of conventions, and it applies to people and agents
alike.
