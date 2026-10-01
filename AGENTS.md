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
Client, person and place names never appear in code, commits, branch names, PR text or issues; use
case codes only.
Commit hooks may fix formatting. Install both with
`uv run pre-commit install --install-hooks -t pre-commit -t pre-push`.

Golden tests are the real acceptance: they run against the reference library (`EMA_REFERENCE`) and
compare against documents the auditor actually delivered. They stay local — client material never
enters git, CI or a bug report.
Reviewers may run `pytest -m "golden and not word"`.

## How work is sliced

Work arrives as a GitHub issue labelled `small` (the issue is the plan; one PR) or `slice` (a parent
issue, a reviewed plan, one `feature/<slice>` PR per layer from child worktrees;
docs/PLAN.md §6.4).
A slice carries its golden acceptance; when it merges, the code and that test are the record —
slice specs are not kept as
files. `dev` merges into `prod` as a release; `prod` is what the auditor runs;
`hotfix/<issue>` starts
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

## Verify, don't recall

Anything that feeds a decision, the code or a deliverable is read from its source in this
session: the code, the contract, the spec, a reference document, a number, a path, an environment
value. Memory from earlier sessions (yours or a tool's) is a pointer to where to look and a record
of preferences and past mistakes, never the fact itself. When memory and the source disagree, the
source wins; say so in your report.

## Building from a slice plan

- The plan's decisions are made. Implement them; if one is wrong or missing, ask. Never pick your
  own name, status code, event type, layout or data shape where the plan names one.
- Anything the plan quotes as a literal (paths, enums, event types, status codes, field names) is
  copied exactly and asserted in a test.
- Every item on the plan's checklist is built, or reported Blocked with the reason. Nothing is
  dropped silently.
- Follow the module next to yours: its structure, naming and error style. The core logic of a
  function is visible on its first screen; no wrapper, factory or helper layer the slice does not
  need.
- Validate input at the boundary with a typed model: malformed input is a 4xx, never a 500.
- State read in two steps can change in between: read it once, in one transaction.
- Wait for a long command with one blocking call; never sleep and re-read its log.
- Before the PR, review your own diff against the checklist and fix what you find. The PR carries a
  table: each checklist item, Done or Blocked, and where (file:line or test name).

## Working as a dispatched agent

- Your brief names the issue, the plan and a handle to notify. Started from an issue without a
  brief: a `small` issue is your plan; a `slice` issue without a plan is a QUESTION. The
  coordinator's handle is in `~/Code/projects/ema/tools/coordinator.handle`.
- Move your issue on the board with `~/Code/projects/ema/tools/board.sh <n> progress` when you
  start and `review` when the PR opens.
- Check that `echo $EMA_REFERENCE` prints the reference library path: golden tests skip without it,
  and a skipped golden is not a pass.
- Word for Mac is shared: before anything that drives Word, ask the coordinator for the Word slot
  with
  a QUESTION message and wait; say when you are done with it.
- No heartbeats or progress messages.
- A fix round on an existing PR keeps its title and appends a short section for the round to its
  description.
- The PR description holds the checklist table (each item Done or Blocked, and where), the golden
  command and its output (no client values), the evidence level reached (docs/PLAN.md §5.16), and
  what Vlad checks by hand. Never merge: Vlad merges.
- When the PR is open, wait for its CI with one `gh run watch <run-id> --interval 90 --exit-status`
  (not `gh pr checks --watch`), then report once with the `worker_done` command from your
  preamble: `orca orchestration send --type worker_done --subject "DONE PR #<n> <head sha>
  checks=<pass|fail>" --outcome <succeeded|failed> ...` with the preamble's IDs. If blocked, ask
  with the preamble's `orca orchestration ask` and wait for the answer.
- Your last message is the complete report, because Orca folds each finished turn to its last
  message: what was done, decisions and why, evidence (tests and goldens, PR, head sha, checks)
  and anything blocked. Send it after `worker_done`, and nothing after it.

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
