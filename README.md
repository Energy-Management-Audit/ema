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

`scripts/dev` runs the UI locally: the API on 127.0.0.1:8766 and Vite on 127.0.0.1:5173, and opens
the one-time sign-in link. `scripts/dev --mock` serves mock data. Zed runs both as tasks (`.zed/tasks.json`).

Configuration uses `EMA_*` environment variables before `settings.toml` in the workspace, then
defaults. Set provider keys with `EMA_GEMINI_API_KEY` / `EMA_OPENAI_API_KEY` for development and CI;
they override OS keyring entries under service `Ema` and usernames `gemini_api_key` /
`openai_api_key`. Keys are never read from workspace settings. `EMA_LLM_LIVE=true` enables live
provider construction and is environment-only.

Golden tests read the real reference library, which lives outside this repository and never enters
git. To run them:

```bash
export EMA_REFERENCE=~/Code/projects/ema/data
# Optional; defaults to ~/Code/projects/ema/artifacts
export EMA_ARTIFACTS=~/Code/projects/ema/artifacts
uv run pytest -m golden
```

## Agents (MCP)

`ema mcp` serves Ema's agent tools over stdio (`docs/PLAN.md` §5.13). Register it in the agent's MCP configuration
as a stdio server with command `uv` and arguments `run --directory <repo> ema mcp`. It uses the CLI's workspace
(`EMA_WORKSPACE`); put input files in `<workspace>/imports/` or pass `--import-root <dir>`.

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
