# Working in this repository

One page, for people and agents alike. The long form is `docs/PLAN.md`; this is what you need
before touching anything.

## What the product is

Ema prepares the paperwork of a Romanian energy-audit firm. Her output goes to clients and to ANRE
under the auditor's name, so two things are not negotiable:

- **A deliverable never mentions AI**, carries no disclaimer and no meta commentary.
- **A number in a deliverable is traceable** to the document it came from, or it is marked as
  missing. Nothing is invented to fill a gap.

## Boundaries

```
interfaces (api, cli, mcp) -> workflows (invoices, piee, audit, reporting)
                           -> domain (consumption_analysis, energy_data, clients)
                           -> core
```

- Workflow modules never import each other; `core` imports nothing else from Ema; interfaces hold
  no business logic. `.importlinter` enforces this — it is a build failure, not a review comment.
- A workflow is one code path. The UI and the CLI call the same use-case function.

## Gates

`scripts/check` is the non-mutating gate run by CI and the pre-push hook: ruff format and check,
the 400-line file limit, pyright strict on `src/`, import contracts, and non-golden unit tests.
Commit hooks may fix formatting. Install both with
`uv run pre-commit install --install-hooks -t pre-commit -t pre-push`.

Golden tests are the real acceptance: they run against the reference library (`EMA_REFERENCE`) and
compare against documents the auditor actually delivered. They stay local — client material never
enters git, CI or a bug report.

## How work is sliced

One slice = one `feature/<slice>` branch = one PR into `dev`. A slice carries its golden
acceptance; when it merges, the code and that test are the record — slice specs are not kept as
files. `dev` merges into `prod` as a release; `prod` is what the auditor runs. `hotfix/<issue>` starts
from `prod` and lands in both.

Commits follow Conventional Commits. Frontend commits and component names carry the design id they
implement (`feat(ui/3c): source snippet in the review row`, `FieldReviewRow` "3c"), so any screen
traces back to the handoff.

## Style

- SOLID where it earns its place: one responsibility per module, small interfaces only at real
  boundaries (readers, document engine, LLM, storage, runner), composition over inheritance, pure
  calculations.
- No abstraction without a second real use. No framework where a function will do.
- Errors surface with context; nothing is swallowed. A failed file or section never fails the job.
- Comments explain a non-obvious *why*, never *what*.
- Code, tests and documentation in English, using the Romanian business terms (anexă, tep, Necesar
  info, Prelucrare date). **UI copy is Romanian, taken verbatim from the design handoff.**
- Romanian number formatting in anything a user reads: `1.234,56` in documents, `1 234,56` in the
  UI, unit after a space.

## Packaging constraints (they shape the code)

The Windows build is a frozen one-folder PyInstaller bundle. Therefore:

- All bundled resources live under one resources tree and are reached through the single path
  helper. No module builds its own path to a bundled file.
- Imports stay static. No dynamic import, no plugin discovery.
- Nothing is ever written next to the executable: the workspace is a configured directory.
- External binaries (Tesseract, Word) are located through configuration, never assumed
  on `PATH`.

`docs/decisions/0001-packaging-and-resources.md` has the reasoning.

## Things that have bitten this product before

- A frozen worker that ignored source edits, and whose stderr was discarded.
- Readers pinned to spreadsheet cell addresses: the client's next file has the label one row lower.
  **Find data by label, never by address.**
- Two code paths for one workflow, with the untested one wired to the UI.
- Review gates that blocked the very step meant to satisfy them.
