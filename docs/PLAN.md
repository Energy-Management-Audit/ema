# Ema: design and plan

The **only** plan and design document for Ema. Update it in place; nothing forks off it.
The design handoff it refers to lives in the reference library (§5.18), together with
`FRONTEND_BRIEF-2026-09-19.md`, the brief that produced it.

---

## 0. How this document is used: broad here, narrower toward Codex

| Level | Where | Contains | Owner |
|---|---|---|---|
| 1. Product | §2–§4 of this doc | who, what, why, requirements, decisions | user + Claude |
| 2. Design | §5–§6 of this doc | modules, data, flows, contracts, rules | Claude |
| 3. Slice spec | the worker's dispatch + PR description (not a file in the repo) | one slice: exact files, signatures, golden case, out of scope, done commands | Claude writes, Codex reviews |
| 4. Code + tests | the repo | implementation; the golden test permanently encodes the acceptance | Codex |

Each level only narrows the one above. If Codex finds the level above wrong or unbuildable, it
pushes back in the spec review, and this document is fixed. Levels never silently diverge.
Slice specs are not stored as files once merged: the code and its golden test are the record,
which keeps the repo free of markdown sprawl.

---

## 1. Checkpoint

- 2026-09-18 **Step 1 done:**
  - Reference library built and verified (206 files, 161 MB, sha256 catalog).
  - 1.4 GB of clutter moved to `~/.Trash/ema-cleanup-2026-09-18/`.
- 2026-09-18 **Step 2 done:** analysis of the real material (§3.2; details in `$EMA_REFERENCE/_analysis/`).
- 2026-09-18 **Step 3 done:** Festival/camp dropped, new repo, git flow, standards (§3.3, §6).
- 2026-09-19 **Step 4 drafted:** architecture (§5) + roadmap (§7) + frontend brief.
- 2026-09-19 CLIENT-A2 final audit + original `.rar` added to the library. **This is the first complete
  input→final audit pair**; its ch. 4 tables supply the 2023–2025 dataset (§9). *Corrected
  09-23: the final was produced with an agent, so only its inputs are used (§5.16).*
- 2026-09-19 pywebview and repo layout confirmed; CLIENT-A2 electrical photos added (the case is
  now complete); Downloads duplicates moved to Trash.
- 2026-09-19 Telemetry: none. Export = deliverables only, import = input data (no job transfer).
- 2026-09-19 **CLIENT-P1 PIEE redone in the auditor's CLIENT-I5 format** (her request of 19 Sep). Vlad
  sends it.
  - The rules are captured as the **PIEE format contract (§5.10)**.
  - The golden and the reference scripts are in the library.
  - Her feedback on it is the first acceptance signal for S8.
- 2026-09-21 **Design handoff received and folded in** (§5.18). The bundle is in the library at
  `$EMA_REFERENCE/design/handoff-2026-09-21/`.
  - Answered: light default + dark toggle · 7a is an export screen, no e-signature · designed at
    1400×900, built resizable from 1280×800.
  - It added R18–R21 (source snippets, undo log, verbatim copy and tokens, per-item errors),
    fields/log/snippet endpoints, and split the frontend slice into S17a (component layer) and
    S17b (screens).
  - Two screens still to design in the same language during S17b: **Clienți** and **Raportare
    manager energetic**.
- 2026-09-21 **Repo swap done (§8):** library out, campaign archived, 21 GB of ARGUS build output
  to the Trash, and `Energy-Management-Audit/ema` created with the skeleton — gates, import
  contracts, empty packages, plan, `AGENTS.md`, ADR 0001 — CI green on `prod` and `dev`.
- 2026-09-23 **Architecture review, round 1 (Codex): 19 findings answered** (11 accepted,
  8 in part, none rejected outright). Applied here:
  - SQLite is the single job store, with field revisions and stage fingerprints (§5.3).
  - Review, decisions and readiness come before the first PIEE (new slice S1b; §5.9).
  - Typed evidence and field states (§5.4, §5.18); the PIEE base's anchor map (§5.10).
  - Office runs behind a supervised adapter (§5.5); Word sets the TOC page numbers, and S0
    proves the PIEE path too (§5.7).
  - Backup and restore (§5.3); the source policy (§5.6); enrichment and loopback boundaries
    (§5.11, §5.15); the real gates and a Windows build from S1 (§6.3); golden evidence levels
    (§5.16).
  - Open for Vlad: §9.
- 2026-09-23 **Vlad's answers to round 1:**
  - The CLIENT-A2 final was produced with an agent, not by the auditor: its inputs stay as test
    inputs, its text is never a reference or base (§5.16). The audit base is AUDIT-01 2026.
  - The goal, restated: her exact results, automated (§2.1). Audits work like the PIEE: her
    latest finished audit filled in, by an AI agent under the hood (§5.7, §5.9 W3).
  - **Mac first**, Windows port after (R17, S18); this replaces round 1's "Windows build from S1".
  - TOC page numbers: Word sets them, on the Mac through AppleScript, proven the same day on the
    approved PIEE (§5.7).
  - The design handoff is implemented as made; Claude draws the missing screens and checks them
    visually (R20, §5.18).
  - the auditor approved the CLIENT-P1 PIEE, pies included (§5.10).
  - Online research: the agent chooses and judges its sources (§5.11).
- 2026-09-23 **Architecture review, round 2 (Codex, the last): 8 findings**, 7 accepted and 1 in
  part:
  - stages are fingerprinted by everything they read, and backup pins files (§5.3)
  - only the backed API is frozen early, and S10 is split from the audit base S10b (§7)
  - a hung Word for Mac is force-quit, restarted and retried (§5.5, Vlad's F3)
  - the outbound-data boundary is enforced in code (§5.11)
  - drafts report traceability coverage, not truth, and vision readings wait for a human (§5.12)
  - final export needs a human approval, and R14 is a policy with guardrails (§5.9)
  - Word edits happen on a working copy (§5.18); the dev loop is same-origin (§5.1)
  - Vlad, the same day: the CLIENT-A2 final was produced with an agent, so it is inputs only,
    and the audit base is AUDIT-01 2026 (§5.7, §5.16)
  - The review is closed; Vlad's decisions on it are F1–F3 in §4.
- 2026-09-23 **Ready for implementation:** the plan is on `dev`, and the S0, S1 and S1b slice
  specs are written (level 3, §0); Codex starts S0 and S1 in parallel.
- 2026-09-23 **Orca replaces Conductor** for running the agents: `orca.yaml` holds the worktree
  setup, and §6.4 describes the coordinator loop. Wave 1 is S0, S1 and S3.
- 2026-09-23 **S1 merged** (PR #4): the gate, workspace, job store, backup/restore, CLI and
  `/health`, after two coordinator review rounds and an adversarial review (5 findings, all fixed).
  The same day: LibreOffice dropped from the project (Word is required for conversion, TOC page
  numbers and the preview), and S9 split into S9a/S9b.
- 2026-09-24 **Checkpoint:** `dev` holds S0, S1, S1b, S2, S2b, S3, S9a and S10 (PRs #4–#12), each after a spec
  critique, a coordinator review and an adversarial review. S9 families re-split (§7): S9b takes OMV Petrom and
  ALIVE, whose invoices its golden needs.
- **Next:**
  1. ~~Vlad's final decisions on the review~~: F1–F3 decided 09-23 (§4).
  2. ~~The S0, S1 and S1b slice specs~~: written 09-23. S1 also aligns `AGENTS.md` and ADR 0001
     with §5.3, §5.5 and §6.3.
  3. Claude draws the missing screens (§5.18); needed before S16a.

---

## 2. Product

### 2.1 What Ema is

- **Ema** is a female-persona AI assistant for **Energy Management & Audit SRL** (the auditor
  AUDITOR, lead auditor / attested energy manager). The name reads as both "Energy Management
  Assistant" and E.M.A.
- She prepares EMA's recurring paperwork so the auditor can focus on analysis, site visits and
  client relationships.
- **The goal (Vlad, 09-23): automate the auditor's workflows by producing her exact results.** Every
  deliverable is her own document — her template, same style, same layout — filled in for the
  client, as the approved CLIENT-P1 PIEE is. Under the hood an AI agent does the filling where rules
  cannot (the audit); nothing in the output differs from what she would make.
- The UI speaks as Ema, in Romanian. Code, documentation and specs are in English, using the
  Romanian business terms (anexa, tep, Necesar info, Prelucrare date).

### 2.2 Users and scale

- **Now: Vlad on his Mac, through the UI** (decided 09-23). He runs the PIEEs and audits with the
  app until it works well; the Windows port comes after (R17).
- **Then: the auditor** (and later possibly colleagues) on **Windows**, through the UI. She will
  eventually do most of the work.
- **Vlad + AI agents** headless (CLI now, MCP later): bulk runs, fixes, automation.
- **Scaling goal:** more clients and audits **without more staff**, i.e. agents doing more of the
  work, and possibly a hosted platform where clients upload documents and drafts come out largely
  on their own.
  - **Built now:** everything runs as jobs that an agent can drive, and nothing assumes a single
    local machine (§5.3).
  - **Not built now:** multi-tenancy, billing, hosting.

### 2.3 Workflows

| # | Workflow | Input → output | Nature |
|---|---|---|---|
| W1 | **Facturi** (invoices) | supplier invoice PDFs (text or scanned) → one verified Excel workbook per client | deterministic |
| W2 | **PIEE** (energy-efficiency programme, yearly per client) | Anexa 2–3 + Necesar info (+ previous years or the auditor's *Prelucrare date*) → her latest PIEE with the client's content (§5.10) (+ *Prelucrare date* workbook) | deterministic |
| W3 | **Audit energetic** (weeks-long job) | client dossier + questionnaire + site-visit material + online sources → Word audit in the auditor's structure | deterministic + AI |
| W4 | **Raportare manager energetic** (yearly, all clients) | all clients' Anexa 2–3 → the auditor's report workbook | deterministic |
| W5 | **Prelucrare date** (calc workbook) | questionnaire + previous years → the auditor's workbook layout; also accepted as an input | deterministic |

Out of scope for now: the prospecting list (Anexa 3 public emails), the website.

### 2.4 Requirements (numbered, referenced by slices)

**Output fidelity**
- R1 Audits and PIEEs match **the auditor's current documents**: same chapter/subchapter structure,
  layout, look and level of detail (§3.2). Her real documents are the only design basis;
  generated drafts are never reference material.
- R2 Deliverables are final client documents: **no AI warnings, disclaimers, meta commentary**
  or notes about how they were produced.
- R3 **Keep her structure; update figures, charts and interpretations** (her rule of 12 Sep).
  The same structure is re-filled each year.
- R4 Later, optionally: a modernized "Ema" house style with the same structure, layout and detail.
- R4b **Styling, fonts and visuals are kept exactly** as in the auditor's template (user, 2026-09-19:
  „imperative").
- R4c **Missing data in a deliverable is marked briefly in red** (e.g. „date indisponibile") at the
  exact place it would appear, with no explanatory text. Sections are otherwise kept as in her
  template.
- R4d **Deliverables are standalone:** no external links; chart data is embedded in the `.docx`.
- R4e **The PIEE follows the PIEE format contract (§5.10):** her latest finished PIEE, with only
  the client content changed.

**Data**
- R5 **Supplied first, online for the rest.** Use the client's data first, look up whatever is
  missing online, and map it in with its source.
- R6 **Equipment enrichment is autonomous** (today the auditor does it by hand with AI: look up the
  equipment, describe it, explain its purpose).
- R7 Chapters/sections can be marked **later** (waiting for a visit, thermography or electrical
  measurements) and **never block** other sections.
- R8 *Prelucrare date* is **generated by Ema and also accepted from the auditor**; hers is
  authoritative for the years it covers.
- R9 Old formats: `.xls` read directly; `.doc` converted automatically; originals kept.
- R10 Anexa 2–3 measure commissioning date = **column C, a year** (from the documents).

**Invoices**
- R11 The **current extractor output format is the accepted contract** (the auditor prefers it). Only
  failures are hardened.
- R12 **Electricity only** for now. Gas invoices stay stopped. SEE re-invoicing documents are to be
  supported later (low priority).

**Operation**
- R13 Every workflow runs **without the UI** (CLI/agents), with the same code path as the UI.
- R14 Agents may prepare and draft; **only a human marks audit sections done and exports the
  final version**. On one machine where agents run under the same account with a shell, Ema
  cannot tell a human from an agent, so this is an **operating policy with guardrails** (§5.9),
  not a security boundary.
- R15 AI providers: **OpenAI and Gemini** (allowed to see client documents).
- R16 Maps: a free source first (OpenStreetMap-based, attributed). Otherwise the map is a `later`
  item that the auditor fills from Google Maps.
- R17 **Mac first, then Windows** (decided 09-23): the app is built and used locally on Vlad's
  Mac until it works well, then ported to Windows for the auditor. Vlad's Windows PC is the Windows
  test machine. Nothing Mac-only enters the code: the port adds, it does not rewrite.

**Interface (from the design handoff, 2026-09-21 — §5.18)**
- R18 **Every proposed value opens its evidence:** the page crop with the value highlighted, the
  sentence around it, and why it is uncertain; `sheet!cell` or a range for spreadsheets; URL, date
  and quote for online facts; the inputs of a calculation. Where no highlight is possible (a
  converted `.doc`, a failed OCR box) the snippet says so instead of guessing.
- R19 **Every accept, correction and bulk action is reversible and logged** in the job's „Jurnal".
- R20 **The UI is the handoff, implemented as made** (Vlad, 09-23: a design he likes, not a
  suggestion): its layout, tokens, components, states and ids; paper never inverts; the focus
  ring is never removed without its replacement; Romanian copy verbatim. The only adaptations are
  resizing across desktop sizes and the data corrections of §5.18.
- R21 **Errors and empty states are per item and actionable:** the concrete cause, and the next
  step or two real exits. A failed item never stops the rest.

---

## 3. What we learned

### 3.1 The current system (ARGUS)

- About 130k LOC in four layers: React → Tauri (Rust) → Rust platform core → pre-built Python
  worker over stdin/stdout. The audit module alone is 62k LOC with ~75 SQLite tables per
  project. The legacy standalone tools (2.8–9.2k LOC each) delivered real work.
- **Deadline-run failures:**
  - audit couldn't run without the UI (the API key lived only in Rust)
  - the frozen worker ignored source edits
  - worker stderr was discarded
  - import history was poisoned by old broken files
  - review gates blocked the extraction meant to satisfy them
  - PIEE readers pinned to cell addresses read wrong numbers silently
  - PIEE had two code paths and the UI used the untested one
  - the CLIENT-A1 audit and CLIENT-P1 PIEE had to be produced by an agent calling internals directly
- **Security to-dos (user):**
  - rotate the Gemini key pasted in the 18 Sep chat
  - change the shared mailbox password sent in plain text in the 15 Jul email

### 3.2 The real material (full write-ups in `$EMA_REFERENCE/_analysis/01–03`)

1. **Audit composition:** about 40 % fixed text, 25 % parameterised, 35 % client narrative.
   - Ch. 1 (scope/method, ~8k words) and ch. 7 (financing) are 86–100 % identical across her audits.
   - Ch. 4 = templated sentences with numbers.
   - Ch. 2–3 and the specific measures are client-specific.
2. **the auditor's master structure** (same tree in all her 2026 audits):
   1. Descrierea și scopul auditului
   2. Descrierea și istoricul societății
   3. Descrierea situației existente
   4. Analiza consumurilor energetice
   5. Bilanțurile energetice (only when measured)
   6. Măsuri
   7. Surse de finanțare
3. **Her look:**
   - A4, header „Audit energetic pe întregul contur al {client}"
   - Times New Roman 12, justified, 1.5 line spacing
   - tables with green `00B050` header rows and white text
   - **native Word charts**
   - captions „Fig. nr. X.Y" (below the figure) / „Tabel nr. X.Y" (above the table)
   - every figure and table announced before („În figura numărul…") and interpreted after
     („Conform tabelului numărul…")
   - automatic heading numbering, a Word TOC field
4. **Audit ch. 4 ≈ PIEE:** they share ~50 % of their wording and the same section order →
   one generator for both.
5. **Data sources per chapter:**
   - ch. 2 = registries + questionnaire + online (location, history, map)
   - ch. 3 = received documents + site visit + online equipment enrichment
   - ch. 4 = questionnaire/calc data
   - ch. 5 = the auditor's own measurements (photos of meter/analyser displays + FLIR images, read by vision)
   - ch. 6 = auditor judgement + calculations
6. **Equipment enrichment unit:** row (brand / model / kW / year / process) → image + what it does +
   energy-relevant features, with sources.
7. **Inputs drift by client:**
   - Anexa 2–3: 13 sheet-set variants, contact block moving ±5 rows, 14 variants of the fuel-column
     headers, 2–76 measures.
   - Necesar info: stable carrier blocks.
   - *Prelucrare date*: a stable core of ~10 sheets plus per-client extras, rolling 3 years.
   - → **Every reader goes by label.**
8. **EMA's 13-item document request checklist** (Necesar info „diverse") already numbers the
   dossier files (CLIENT-A1 2.1, 5.x, 9.x…) → completeness + classification.
9. **Invoices:**
   - 29/29 text PDFs (EDS, MET, ENGIE) exportable.
   - All failures are client identity (CLIENT-I2 24; 11 OCR'd ALIVE).
   - MET gas + SEE re-invoicing documents are stopped by design.
10. **Thermography** = FLIR screenshots via WhatsApp (no radiometric data; the overlay is
    readable).
11. **How the auditor's PIEE is actually built (found 2026-09-19 from her CLIENT-I5 PIEE):**
    - All 31 bar charts are **linked charts**: they point at her *Prelucrare date* workbook (in her
      OneDrive) by cell reference, e.g. `'Consum Gaz'!$D$12:$O$12`, and keep a cached copy of the
      values.
    - The 6 pie charts (PV share, energy mix, one per year) are **pasted pictures**.
    - Her CLIENT-P1 workbook uses **the same template layout** as the CLIENT-I5 one; almost every
      chart reference lands on the right cell.
    - So her yearly workflow is: build the client's *Prelucrare date* in her template layout →
      copy last year's PIEE → re-point the chart links → rewrite the numbers in the text and tables.
    - **Design implication (W2 / S5b / S8):** the PIEE generator = generate the client's workbook in
      her exact template layout + clone her PIEE docx + **replace each chart's external link with
      embedded chart data** + refresh the chart caches + turn the pie pictures into native pie
      charts + replace text and tables. The full rule set is the PIEE format contract (§5.10).
    - **The deliverable is standalone (user, 2026-09-19):** no links to external workbooks (her
      CLIENT-I5 links point into her personal OneDrive and break on any other machine). Charts stay
      native and editable in Word (Edit Data) with their data embedded in the `.docx`. The
      *Prelucrare date* workbook is delivered separately, only as a working file. This is higher fidelity than
      building charts from scratch, and it makes S0 much less risky: the native charts already
      exist in her template; only their data changes.

### 3.3 The process

- In 25 days ARGUS accumulated 29 festival phases, ~48k lines of process markdown, 52 evidence
  documents, and 48 commits about evidence or records.
- Generic checkbox gates never tested "does the output match the auditor's document".
- Festival ownership codes became code-level walls, and agents refused to fix "AP-owned" bugs.
- "Synthetic fixtures only" meant nothing was ever accepted against real documents.
- Fest also consumed a lot of usage and context. → **Dropped** (§4).

---

## 4. Decisions log

| Date | Decision |
|---|---|
| 09-18 | Operators: the auditor on Windows via the UI (main operator long term) + Vlad and agents headless |
| 09-18 | New, clean repo; old repos retired later |
| 09-18 | Identity: **Ema**, female persona |
| 09-18 | Invoices: keep the current output format, harden failures; electricity only; SEE later |
| 09-18 | Audits: the auditor's structure/look/detail; only real reports as the design basis; no AI meta text |
| 09-18 | Audit data: supplied first, online for the rest; enrichment autonomous; sections can be "later" |
| 09-18 | Reference library outside git; Downloads cleaned (to Trash) |
| 09-18 | Anexa 2–3 commissioning date = column C (year) |
| 09-18 | **Festival/Fest and camp dropped** for Ema; standards enforced by tools |
| 09-18 | No backup push of ARGUS or legacy repos (accepted: ARGUS is lost when the archive is deleted) |
| 09-18 | Working model: **Claude designs, Codex implements**, both in Conductor |
| 09-18 | Git flow: `prod` / `dev` / `feature/*` / `hotfix/*` (release branches only if needed) |
| 09-19 | AI providers: OpenAI + Gemini |
| 09-19 | Maps: free OSM-based source; otherwise a manual Google Maps screenshot |
| 09-19 | *Prelucrare date*: generated by Ema **and** accepted from the auditor |
| 09-19 | `.xls` read directly, `.doc` converted (Word → flag). *09-23: LibreOffice dropped (Vlad)* |
| 09-19 | Desktop shell: **pywebview + PyInstaller** |
| 09-19 | Repo `~/Code/projects/ema` = `Energy-Management-Audit/ema`; library at `~/Code/projects/ema-reference` |
| 2026-09-24 layout: `~/Code/projects/ema/{code,data,docs,tools,artifacts}` |
| 09-19 | No slice specs are written until the architecture has been challenged with the Codex agent (§10) |
| 09-19 | Two machines: **separate workspaces, no job transfer feature**. **Export** = the files the app produces (the `.docx` / `.xlsx` deliverables); **import** = loading the input data. A hosted backend later |
| 09-19 | Windows distribution: **unsigned installer + in-app update check** (SmartScreen warning accepted) |
| 09-19 | PDF stack: **replace PyMuPDF (AGPL) with pypdfium2 + pdfplumber** during S9, keeping the golden results |
| 09-19 | **No telemetry**; diagnostics on demand only |
| 09-19 | Missing data in deliverables → a short red marker, no explanation (R4c); styling kept exactly (R4b). First applied to the CLIENT-P1 PIEE: missing water and 2025 monthly PV values marked red, both water types kept, the 2025 gas jump presented as is |
| 09-19 | **PIEE = clone the auditor's latest finished PIEE and change only client content**; charts standalone (embedded data), pies native; the rule set is the PIEE format contract (§5.10) with the CLIENT-P1 2026 PIEE as golden |
| 09-19 | Document preview: **paged, scrollable whole-document view (docx → PDF → pdf.js)**; **no in-app editing** (corrections via facts + regenerate; polishing in Word) |
| 09-19 | AI: **no automatic routing**. Gemini is the default, OpenAI optional; the provider and model are chosen manually in Settings from a short curated list (a standard default + one stronger option each; no overkill or underpowered models); costs are logged per job, no cap for now |
| 09-21 | **Design handoff is the frontend reference** (§5.18); `FRONTEND_BRIEF.md` is now only the record of the ask. Authority: HTML > README > this plan, except on what the data is, where the plan wins |
| 09-21 | Theme: **light default + a toggle** in Setări → Aspect; dark is a preference |
| 09-21 | 7a „Predare" is the **export screen**; no e-signature (her signature and stamp are images in her template, and the client submits to ANRE) |
| 09-21 | Window: **designed at 1400×900, built resizable from 1280×800** |
| 09-21 | Design ids (3b, 7d…) are the shared vocabulary: they appear in **component names and commit messages** |
| 09-19 | **Docker: not for the product now** (hosted backend later); **Windows `.exe`: yes** (PyInstaller one-folder + installer, built on a Windows CI runner) (§10) |
| 09-23 | **Review closed (F1–F3):** research queries stay free text, and code refuses any carrying the job's private values (§5.11). R14 is a light policy: the 7a export click in the UI, one y/N in the CLI, and UI-only once the auditor takes over (§5.9). A hung Word on the Mac may be force-quit, since Vlad does not use Word there (§5.5) |
| 09-23 | **D4: the API contract is written early** — S16a follows S1b + S10, and the frontend track runs in parallel with the PIEE backend |
| 09-23 | **Audits work like the PIEE:** her latest finished audit cloned and filled in, same style and layout; an AI agent does the filling under the hood (§5.7, §5.9 W3, §5.12). The goal is her exact results, automated, nothing different (§2.1) |
| 09-23 | **Online research: the agent is free** to find information and judge whether a source is legitimate; no site or field allowlist; every fact stays traceable (§5.11) |
| 09-23 | **The handoff is implemented as made**, resizable across desktop sizes (R20); Claude draws the missing screens in its direction and checks them visually (§5.18) |
| 09-23 | **the auditor approved the CLIENT-P1 PIEE** (Vlad showed it to her): the S8 golden is approved, and the pies stay exactly as made |
| 09-23 | **Mac first, Windows after** (R17): quick development to get the app working locally and well; Vlad runs the jobs with it meanwhile; then the Windows port (S18) on Vlad's Windows PC |

---

## 5. Architecture

### 5.1 Shape and runtime

```
      the auditor: Ema desktop window (Windows)        Vlad / agents: CLI (MCP later)
                     │ HTTP on 127.0.0.1                    │ direct Python calls
   ┌─────────────────▼──────────── interfaces ──────────────▼─────────────┐
   │  api/ (FastAPI + OpenAPI, serves the built frontend)   cli/   mcp/     │
   └──────────────────────────────┬────────────────────────────────────────┘
                                  │ use-case functions only
   ┌──────────── workflow modules (never import each other) ───────────────┐
   │     invoices        piee        audit        reporting                  │
   └────────┬──────────────┬──────────┬────────────┬────────────────────────┘
            │              └────┬─────┘            │
            │         consumption_analysis         │    shared domain modules
            │                   │                  │
            │              energy_data ────────────┘
            │                   │
            │                clients
   ┌────────▼───────────────────▼──────── core ─────────────────────────────┐
   │ workspace · jobs · office (xls/xlsx readers, docx engine, native charts, │
   │ convert) · pdf/ocr · llm · web · config · secrets · logging · errors    │
   └──────────────────────────────────────────────────────────────────────────┘
```

- **One Python package (`ema`, Python 3.12, uv), one process.**
- **Desktop:** the same process shown in a native window by **pywebview**, packaged by PyInstaller
  into one Windows installer.
  - pywebview is a small library that opens an OS window displaying a web page with the browser
    engine already in the OS (Edge WebView2 on Windows 10/11, WebKit on macOS), plus native file
    dialogs.
  - Nothing else is needed: no Electron (+~150 MB Chromium, Node) and no Tauri (Rust shell +
    separate Python sidecar, which is what ARGUS did).
  - What it lacks compared with those frameworks: native OS extras such as the menu bar at the top
    of the Mac screen, right-click menus outside the web page, a system-tray icon and built-in
    auto-update. Ema's own menus inside the window are unaffected; the rest can be added later if
    ever needed.
- **Dev loop:** `uv run ema serve` + `npm run dev` in a normal browser, **same-origin**: the Vite
  dev server proxies `/session`, the API routes, `/evidence` and SSE to `ema serve`, so the browser
  sees one origin and the §5.15 checks stay on. Integration checks run the built frontend served by
  FastAPI. S16a acceptance includes this two-process loop. A frozen build only for releases.
- **Dependency rules** (enforced by `import-linter` in CI):
  - `interfaces → workflow modules → {consumption_analysis, energy_data, clients} → core`
  - Workflow modules never import each other.
  - `core` imports nothing from Ema.
  - Interfaces contain no business logic.

### 5.2 Modules and what each owns

| Module | Owns | Public entry points (use cases) |
|---|---|---|
| `core.workspace` | workspace folders, content-addressed files, file slots + versions | `add_file`, `set_slot`, `list_versions`, `remove_version` |
| `core.jobs` | the job store (SQLite, §5.3), stage runs + fingerprints, runner, cancellation, progress events | `create_job`, `run_stage`, `cancel`, `status`, `subscribe` |
| `core.review` | fields and their evidence, decisions (the Jurnal), conflicts, undo — the same for every workflow | `fields`, `decide` (accept / correct / reject / choose), `undo`, `conflicts` |
| `core.office` | xls/xlsx label-finding readers, file-type sniffing, docx block engine, native charts, the supervised Office adapter (§5.5) | `find_label`, `read_block`, `sniff`, `render(template, blocks)`, `convert_doc`, `render_pdf`, `update_toc_pages` |
| `core.pdf` | text extraction, OCR (Tesseract ron+eng) | `text(pdf)`, `ocr(pdf)` |
| `core.llm` | OpenAI + Gemini behind one interface, structured output, the tool-calling agent loop, cost logging | `complete_json(schema, prompt, context)`, `run_agent(instructions, tools, context, limits)` |
| `core.web` | allow-listed HTTP fetch + search for enrichment, caching, rate limits | `search`, `fetch` |
| `clients` | client identity (CUI, name, addresses, CAEN, contacts, sites), ANAF lookup | `get_or_create_by_cui`, `refresh_from_registry` |
| `energy_data` | canonical per-client/year dataset, carrier vocabulary, factors, readers, calculations, *Prelucrare* writer | `import_anexa`, `import_necesar_info`, `import_prelucrare`, `build_dataset`, `indicators`, `write_prelucrare` |
| `consumption_analysis` | PIEE / audit-ch. 4 blocks (tables, native charts, phrased commentary) | `blocks(dataset, scope)` |
| `invoices` | the ported extractor, batch identity, workbook export | `extract_batch`, `confirm_client`, `readiness`, `export` |
| `piee` | PIEE job | `generate(client, year)`, `readiness`, `export` |
| `reporting` | energy-manager report | `generate(years, clients)` |
| `audit` | the audit job: intake, extract, enrich, facts, sections, draft, render | stage functions (§5.9), `readiness`, `export` |

### 5.3 Storage, jobs and the scaling path

```
<workspace>/                              default %APPDATA%\Ema (Windows), ~/Ema (mac); configurable
  ema.sqlite                              the job store: clients, files, slots, jobs, stage runs, fields,
                                          decisions (the Jurnal), sections
  clients/<client-slug>/
    files/<sha256>.<ext>                  every uploaded/converted file once; immutable
    jobs/<year>-<type>-<short-id>/
      work/<stage>/<run-id>/              stage artifacts (dataset.json, facts.json, sections/<id>.json,
                                          enrichment/); immutable once the run ends
      cache/                              rebuildable (page renders, OCR text)
      outputs/                            deliverables (.docx / .xlsx), one per run, versioned, never overwritten
      edits/                              working copies opened in Word („Deschide în Word"); never an output
      log.jsonl                           steps, warnings, errors + tracebacks, LLM calls (model, tokens, cost)
```

- **One authority: SQLite.** Everything that changes — slots, field values, decisions, section
  statuses, job status — lives in `ema.sqlite` and changes in one transaction. Files are either
  immutable (inputs, stage artifacts, outputs) or rebuildable caches, so no file can disagree with
  the database. There is no `job.json`; the diagnostics bundle writes a snapshot of the job's rows.
  `log.jsonl` is the technical log, not state: the Jurnal (R19) is the `decisions` table.
- **Revisions.** Every mutable row a stage can read carries a revision: fields, slots (the
  active version), section statuses, the client record, and the job's settings (provider,
  model). A decision names the revision it was made on, and a decision on an outdated revision is
  refused (HTTP 409 / a CLI error), never applied over the newer value. This is the real race: a
  stage re-run proposing values while the auditor accepts them.
- **Stage fingerprint** = the read set — every `(row, revision)` the run read, recorded by
  `core.jobs` as it reads — + the input file hashes + the template, factor-table and prompt
  versions + the model + the Ema version.
- **Publishing checks the read set.** When a run ends, and again at final export, the read set is
  compared with the current revisions in the same transaction that publishes. On a mismatch the
  artifact is stored as `stale`, not as current, and so is everything downstream of it (§5.9
  section transitions). A test changes a slot and a section decision in the middle of a run.
- **Undo = a compensating decision** against one Jurnal entry. If a later decision changed the
  same field, the undo is refused and names the entry that superseded it; nothing cascades
  silently.
- **File slots with versions.** Each job declares named slots (`anexa_2_3`, `necesar_info`,
  `prelucrare_date`, `dossier[]`, `visit[]`, `invoices[]`). A new upload or conversion adds a
  version; the newest is active; any version can be removed from the slot. Nothing is ever
  "stuck in history". A slot that holds many files is a collection: its slots are named
  `<collection>/NNNN` (`invoices/0001`, …), numbered in upload order, listed with `list_slots` and
  read together with `read_slots`, which records every slot read for the stage fingerprint.
- **Job lifecycle:** `created → running(stage) → ready | failed | cancelled`. Audit jobs stay
  `open` for weeks, and each stage can be re-run.
  - A stage run is recorded with its fingerprint, duration, outcome, warnings and error.
  - **A failed file or section never fails the whole job.**
- **Runner:** in-process worker threads (a single user). `core.jobs` is the only place a stage
  is started, so a hosted version replaces that module's internals. No pluggable runner interface
  until a second runner exists.
- **Portable, not abstracted:** relative paths in the job store; `core.workspace` is the only
  module that touches workspace files; plain SQL. Secrets come from the OS keyring (the auditor) or
  the environment (agents, CI): two real sources behind one function. Storage, queue and
  database adapters for a hosted version (S3, Postgres) are designed only when that version is.
- **Backup** = a consistent snapshot, never a copy of the live folder: SQLite's online backup
  API, every file the job store references, and a manifest with checksums, in one dated zip.
  Backup and file garbage collection take the same workspace lock, so no referenced file can
  disappear while the zip is written. **Restore** opens a backup as a new workspace after
  verifying the manifest. S1 tests backup → restore into a clean folder → the same jobs list and
  export, and a backup running while a job is deleted. Shipped before the first real
  deployment (§10.3).
- **Delete** is two-step: the rows are marked deleted in one transaction, then the folders are
  removed; an interrupted delete is finished on the next start. Removing a slot version only
  unlinks it. A file is garbage-collected only when no slot version, stage run or output
  references it.
- **Export** = the deliverables the app produces (`outputs/*.docx|.xlsx`), saved wherever the user
  chooses. **Import** = loading input files into a job's slots. There is no job transfer between
  machines: each machine has its own workspace (decided 09-19).

### 5.4 Data model (the key types)

- **`Evidence`:** one immutable piece of proof for a value
  - `{id, file_sha?, locator, method, retrieved_at, quote?, highlight}`
  - `file_sha` names the exact file version (content-addressed), so evidence never drifts to a
    newer upload.
  - `locator` is typed: `pdf_region {page, bbox}` · `pdf_text {page, span}` · `cell {sheet, ref}`
    (a cell or a range, `F2!C14:C25`) · `docx {paragraph | table, row, col}` · `photo {region?}` ·
    `url {url, snapshot_sha}` · `manual {who, note?}`
  - `highlight ∈ exact | page | none` — what the snippet can honestly show (R18). OCR keeps its
    word boxes (Tesseract TSV), so a scan gets `exact` when the word is found.
  - `method ∈ questionnaire | anexa | prelucrare | invoice | form | online | manual | calc`
  - Readers capture evidence as they read: it is part of every reader's acceptance (S4, S5, S9,
    S12), with a crop/quote test on a scanned PDF and a spreadsheet.
- **`Value[T]`:** `{value?, unit?, evidence[], derivation?, state, presence, review, revision}`
  - `state` = where it came from: `supplied | extracted | enriched | calculated | manual`
  - `presence` = what Ema's search found: `found | not_found | failed` (`not_found` = no expected
    source has it, and the UI asks for it; `failed` = a reader error with its cause, R21)
  - `review` = what the auditor did with it: `pending | accepted | corrected | rejected`.
    `rejected` is a verdict on a found value; readiness then treats the field as missing.
  - `derivation` (calculated values): `{formula_id, inputs: field ids, factor_version}`; the
    snippet shows the inputs, each with its own evidence.
  - A value is absent exactly when `presence` is not `found` and nobody typed one; a typed value
    is `state: manual` with `manual` evidence.
  - its history is the job's decisions: `{id, at, actor (ema|user|agent), field, on_revision,
    action, before, after, batch_id?, undone_by?}` — each one undoable per §5.3, bulk accepts
    included (R19)
  - Two conflicting values are both kept as alternatives, each with its evidence, and the job
    shows a conflict until one is chosen.
    „Accept exact matches automatically" (3i) may pre-accept identical values (never vision
    readings, §5.12); they stay in the log and can be undone.
- **`Client`:** CUI (normalized), legal name, registration no., address, work sites,
  CAEN + description, contacts, energy manager, ownership.
- **`EnergyDataset(client, years)`:**
  - `carriers[carrier][year][month] → Value` (the closed carrier vocabulary is below)
  - `production[product][year][month]`
  - `economics[year]`: turnover, energy costs
  - `employees[year]`, `vehicles[]`, `buildings[]`, `equipment[]`
  - `measures_existing[]`, `measures_planned[]`: description, commissioning year (col. C), cost,
    savings MWh/tep/lei
- **Carrier vocabulary:**
  - electricity_grid, electricity_pv, natural_gas, diesel, petrol, lpg, fuel_oil, clu, coal, coke,
    wood, biomass, sunflower_husks, biogas, ctl, purchased_heat
  - water_potable, water_industrial, water_storm
  - An alias table maps every header seen in real files („Gaze naturale", „Coji de floarea
    soarelui", „Alți comb. – GPL"…).
- **`Indicators(dataset)`:** tep per carrier and total, shares, specific consumption per
  production unit, energy intensity (tep / 1000 lei), emissions (t CO₂), year-over-year changes,
  trend direction.
- **`Facts`** (audit): typed per section, e.g.
  - `CompanyFacts`, `LocationFacts`, `SiteFacts` (land, buildings)
  - `ProcessFacts[]` (section, stages with purpose, equipment refs)
  - `UtilityFacts` (water, electricity, gas/heat, fuels, compressed air), `LightingFacts`,
    `FleetFacts`, `MeteringFacts`, `AutomationFacts`
  - `EquipmentFacts[]` (+ enrichment), `MeasurementFacts` (visit), `MeasureFacts[]`
  - Every field is a `Value`.
- **Field catalogue** (per workflow, per template version): key, type, unit, `required` (for a
  final).
- **`SectionStatus`:**
  - `ready | missing(facts) | later(visit | thermography | electrical | map) | n/a | drafted | done`
  - plus a `stale` flag (an input in the draft's fingerprint changed); transitions in §5.9

### 5.5 Readers and legacy formats

- **Label-based readers:** find a label (case/diacritics-insensitive, alias list), then read
  relative to it. Regions are always found by label; inside a recognized form version, a
  documented relative column is allowed (the commissioning year in column C, R10). No absolute
  cell address is ever used to find data.
  - **Anexa 2–3:**
    - both form generations; sheet-name aliases (the 6 variants of „Solutii EE…")
    - contact block located by label
    - fuel columns identified by header text → carrier vocabulary
    - dynamic measure lists (TOTAL rows excluded)
    - commissioning year from column C
  - **Necesar info:** carrier blocks „Consum …" → month row → unit row, 1 or 3 years; equipment,
    fleet and building sheets; free-text notes tolerated.
  - ***Prelucrare date*:** the core sheets by name + label; authoritative import for the years it
    covers.
- **Every reader returns data + a list of issues** (missing / ambiguous / unit mismatch). Reading
  never silently guesses.
- **Legacy formats:**
  - File type detected from content, not extension (catches HTML saved as `.xls`).
  - `.xls` read directly (`xlrd`).
  - `.doc` converted on intake:
    1. Word automation through the supervised adapter below (AppleScript on the Mac, COM from the
       Windows port)
    2. otherwise flagged *needs conversion* (the rest continues). There is no second converter:
       LibreOffice is not part of Ema (Vlad, 09-23).
  - The converted `.docx` is a new version (`converted_from`), and word/table counts are checked
    against the original.
- **External programs run supervised, outside the app's process.** Tesseract is called from a short-lived child process that the app waits on with a per-item timeout. On
  a timeout or crash the child is killed, temporary files are removed, the item fails with its
  cause (R21), and the rest continue.
- **Word for Mac (now) is Ema's to restart.** Vlad does not use Word on this Mac for his own
  documents (09-23), so a hung Word may be force-quit. Killing `osascript` alone does not stop
  Word, so Ema acts on Word itself:
  - Word calls are serialized. Ema works on its own copies, under unique names in its folder
    inside Word's container.
  - Every call has an AppleScript timeout. On a timeout Ema force-quits Word, removes its copies,
    relaunches Word and retries the item once with a fresh copy under a new name (so no stale
    lock blocks it). A second failure fails that item with its cause (R21), and the batch goes
    on.
  - A missing Automation permission (AppleScript error -1743) is reported with the steps to grant
    it.
  - S0 tests a denied permission and a forced timeout: Word is restarted, the item is retried,
    and the batch continues.
  - This holds only while Word on the machine is Ema's alone. On the auditor's PC her Word is never
    touched (below).
  - **At the Windows port**, Word runs in a supervised child: `Ema.exe` itself started with an
    internal subcommand, driving a private Word instance recorded by PID, which is killed with it.
    **the auditor's own open Word is never touched.** Word calls are serialized, one instance at a
    time; COM is initialized and torn down inside the child, never in the app's threads.
  - Cancelling a job stops after the current item or kills the child. A job always reaches a
    terminal state (`cancelled` / `failed`); nothing stays „running" forever.
  - The same adapter does the `.docx → PDF` render (preview) and the TOC page numbers (§5.7).
  - Domain work stays on threads (ADR 0001, rule 5): these children are process boundaries that
    Office already imposes, not a worker pool.

### 5.6 Calculations and factors

- Pure functions over `EnergyDataset`, no I/O.
- **Factors** (tep/MWh conversions, e.g. 1 MWh = 0.086 tep; fuel t → tep; CO₂ factors) are
  versioned by year with their source (from the auditor's „Principali factori", „Factori de
  conversie in MWh" (Eurostat) and „impact de mediu" sheets). A factor change never rewrites a
  past job.
- **Verified** by reproducing her *Prelucrare date* numbers (CLIENT-P1, CLIENT-P2, CLIENT-A3).
- **Source policy, per field and year.** When sources differ, Ema proposes a winner in this order
  and shows the conflict for a human to choose; nothing is averaged or adjusted:
  1. the auditor's *Prelucrare date*, for the years it covers (R8)
  2. Necesar info
  3. Anexa 2–3
  4. last year's job

  Her answer to §9 („which one wins") can change only this order, not the mechanism, so S8 does
  not wait for it.
- **Filed and recomputed values are both kept**, each with its evidence and the recomputed one
  with its derivation. The document shows the chosen one.
- **Units and precision:** values are stored at full precision in their source unit; rounding
  happens only at presentation (§5.10 formats).
- **Reconciliation tolerance:** a recomputed total matches a filed one when the difference is
  within the rounding both carry (half a unit of each input's and the filed value's last shown
  decimal, propagated through the sum). Anything larger is a conflict (the §5.10 „Date anuale"
  cross-check).
- **Her workbook's factors are read with her values.** When her *Prelucrare date* is imported, the
  factors on its sheets are recorded with it; a difference from Ema's factor table shows in the
  conflict's derivation instead of being recomputed away.
- Goldens cover a matching total, a real mismatch, and a year without monthly data (CLIENT-P1
  2025 PV). If the library holds no real mismatch, S3 uses a unit fixture and says so.

### 5.7 Document engine (template + slots + blocks)

**Who writes what.** The agent never edits Word or the `.docx`. It works on data:
1. **The agent** returns each section as JSON in that section's schema (a pydantic model derived
   from her section in the base) — for „2.3 Istoria companiei", say,
   `{paragraphs: [{kind: body, text: "Societatea a fost înființată în {{f:founded_year}}…"}]}`;
   for a table, its rows; for a figure, which chart or photo. **The agent never types a number:**
   it writes a reference to a recorded fact, and the engine inserts the value, formatted the
   Romanian way. A number it needs that is not a fact yet (a percentage change) it gets from a
   calculation tool, which records it as a calculated fact first.
2. **The engine** (deterministic Python, the way the CLIENT-P1 script works) opens her document,
   finds the section's anchors, and writes the content into her own paragraphs, tables and
   charts, inside her runs, cloning her element where the client needs more of them.
3. **Word** then lays the result out: TOC page numbers and the PDF (below).

The schema in between is what makes the output checkable and repeatable: every number is matched
to a fact, and every leftover or AI mention is caught, before anything reaches the document.
Regenerating a section rewrites only its anchors.

- **Templates** in `templates/`, built from the auditor's real documents:
  - `audit_master.docx`: **her latest finished audit, cloned** exactly as the PIEE is, with its
    anchor map. **Provisional base: AUDIT-01 2026**, her latest own audit in the library (last
    saved 6 Aug). The CLIENT-A2 final is newer but was produced with an agent, so it is never a
    base or a style reference (R1). the auditor may name another (§9); a change of base re-runs S10b
    only; the §5.10 anchor rules and leftover check apply.
    Fixed chapters (1, 6.1–6.2, 7), header, footer, styles, green tables, captions and the TOC
    stay verbatim; client sections are filled in place. Where a client needs more or fewer of a
    unit (a process, an equipment table, a measured panel, a carrier), the engine clones her own
    heading, paragraphs, table and figure for it, so every added part is formatted exactly like
    hers. A test case is never filled into its own base.
  - **Her reference set: all her own audits in the library, used together** (Vlad, 09-23). One
    document is the base to clone (AUDIT-01), but all of them feed the rest:
    - her 2026 audits: **AUDIT-01, AUDIT-02, AUDIT-03, AUDIT-04**, and **AUDIT-05** (`Cap 2-3-4 V2`,
      ch. 2–4). They are the source for the section catalogue and its variants, the phrase bank,
      the agent's style guide and worked examples, and the prototypes for a section or unit the
      base lacks. They share her template and styles, so a prototype taken from one of them fits
      the base.
    - **CLIENT-A3 2022** is the older template, by the previous auditor: a content and domain
      reference only (what a section covers, what data it needs), never style, layout or wording.
    - The CLIENT-A2 final: never (§5.16).
  - `piee_master.docx`: **her latest finished PIEE kept verbatim** (today the CLIENT-I5
    `MODEL_2026.docx`) plus its anchor map, which classifies every element as fixed or variable
    (§5.10). Client content is replaced in place per §5.10, never re-laid out.
  - `energy_manager_report.xlsx`, `prelucrare_date.xlsx`: her layouts
- **Slots:** named anchors in the templates (e.g. `ch2.date_generale`, `ch4.electricitate.grafic`).
  A slot left unfilled in a draft shows a marker (`[de completat]` in an audit draft, the red
  marker of R4c in a PIEE). What blocks a **final** export is the workflow's readiness (§5.9).
- **Blocks** are instantiated from prototypes taken from her document (a paragraph of that
  style, her table, her caption, her chart), never styled from scratch: Paragraph, BulletList, Table (house style; header row green/white; widths
  from content), Figure (image + caption), **NativeChart** (a real Word chart with its embedded
  worksheet: column/line/pie, her colours), PageBreak. Numbering of figures and tables, and the
  „În figura numărul X… / Conform tabelului numărul Y…" references, are resolved in one pass
  at render.
- **Output settings:**
  - **TOC page numbers are written by the engine**, into the existing entries (her spacing kept),
    with no update-fields prompt on open (§5.10). Writing them is easy; *knowing* them needs a
    layout engine, because a `.docx` holds no pages: where a heading lands depends on fonts, line
    breaks, table heights and chart sizes, worked out only when a program lays the document out.
  - **Word lays the document out, on the Mac too.** Through the Office adapter, Word for Mac is
    driven by AppleScript: open the filled `.docx`, *update page numbers* on the TOC (numbers
    only; entries and spacing untouched), save, *save as PDF*, close. **Proven 2026-09-23** on a
    copy of the approved CLIENT-P1 PIEE with all 28 TOC numbers scrambled to 99: Word restored
    exactly the approved numbers, the TOC paragraphs were unchanged, and the PDF had its 33 pages.
    Needs the macOS Automation permission for Word (granted), and the files placed in Word's
    sandbox container (`~/Library/Containers/com.microsoft.Word/Data/`) for the operation, then
    copied back, so Word never asks for file access.
  - **From the Windows port:** the same steps through COM.
  - **Without Word** (CI, a machine without Office): the TOC page numbers cannot be set and no PDF
    preview is made. A draft keeps its template's numbers and says so; the check reports the
    numbers as not set, and a final export is refused. Word is required for a final document
    (LibreOffice dropped, Vlad 09-23).
  - Added or removed headings keep their `_Toc` bookmarks and the entries' `PAGEREF`s in step.
  - Romanian number formatting (`1.234,56`).
  - Fonts with full Romanian diacritics in charts.
- **Annual reuse:** a client's confirmed facts carry into next
  year's job. The engine re-fills the same template. It never diffs Word files.
- **Risk:** python-docx has no chart support. Native charts are built as raw chart parts
  (DrawingML + an embedded xlsx).
  - **Partly proven (2026-09-19, CLIENT-P1 PIEE):** the result opened cleanly in Word for Mac,
    with editable data. That covered rewriting her existing chart parts, embedding their
    workbooks, and adding native 3D pies.
  - **Her audits link their charts too** (found 09-23): all 30 charts of AUDIT-01 point at her
    OneDrive copy of the client's Necesar info (`'Consum Gaz'!$C$7`…). So the audit base needs the
    same link → embedded-workbook rewrite as the PIEE, and it is one piece of code for both.
  - **S0 still proves, in Word for Mac** (Windows Word again at the port), three separate
    things; none stands in for another:
    1. the PIEE path, as a repeatable check: the CLIENT-P1 golden (rewritten charts, removed series
       and figures, embedded workbooks, native pies) opens without repair, Edit Data works on a
       bar chart and a pie, and the package has zero external relationships and one workbook per
       chart
    2. the audit path: one of her audit charts cloned for a carrier her base lacks, and one built
       from scratch (the fallback), open, are editable, and match her chart
    3. the TOC page numbers (§5.7), productized: Word's update on a scrambled golden restores the
       approved numbers and keeps her TOC formatting (proven by hand on 2026-09-23)

### 5.8 `consumption_analysis`

This generates the section order shared by the PIEE and audit ch. 4:
producție → consum per purtător → consum echivalent (tep) → concluzii → eficiență / consum
specific per purtător → intensitate energetică → impact de mediu (+ audituri/investiții for the
PIEE).

- **Per section:** her table layouts, native charts (monthly per carrier, annual structure,
  trends), and sentences from **her real phrase patterns**, with numbers inserted and rule-based
  choices (creștere/scădere/constantă; the largest share; notable months).
- Deterministic; no LLM.
- The phrase bank is extracted from all her own 2026 audits and her PIEEs (S7; §5.7 reference set).
- **Two consumers, one analysis:**
  - Audit ch. 4 does the same in her audit's own ch. 4 tables and charts, cloned per carrier where
    the client has more than her base.
  - The PIEE writes the same numbers and phrases into her existing tables, charts and sentences
    (§5.10).

### 5.9 Workflows in detail

**Readiness: one function per workflow.** `readiness(job) → {draft_ok, final_ok, blocking[],
warnings[], next[]}`. The CLI (`ema job checks`), the API (`/export/checks`) and 7a all show its
answer, and export calls it; no interface keeps its own rules.

| Workflow | Draft export | Final export is blocked by |
|---|---|---|
| W1 Facturi | n/a (the workbook is the only output) | an unconfirmed batch client. Flagged invoices export flagged, as in today's contract (R11) |
| W2 PIEE | always: missing data in red (R4c); an unresolved conflict renders its proposed value and is listed | an unresolved conflict (the „Date anuale" cross-check included), a failed §5.10 package check, an untouched variable anchor (§5.10) |
| W3 Audit | always, with `[de completat]` markers | a section not `done` or `n/a`, a `stale` section, an unresolved conflict in a fact a section uses |
| W4 Raportare | n/a | nothing: gaps go to the Exceptions sheet |

**Audit section transitions:**

| From → to | Who | When |
|---|---|---|
| `missing` ↔ `ready` | Ema | computed from the facts the section needs |
| `ready` → `drafted` | Ema or an agent | the Draft stage ran |
| `drafted` → `done` | **a human only** (R14) | |
| `done` → `drafted` + `stale` | Ema | an input in the draft's fingerprint changed; the Jurnal records which |
| `drafted` + `stale` → `drafted` | Ema or an agent | the section was re-drafted |
| any → `later(reason)` | a human; Ema only for visit / measurements / thermography / map while that material is absent | |
| `later` → computed | a human, or Ema when the awaited material arrives | |
| any ↔ `n/a` | a human only | |

**Human-only actions (R14), guardrails not security:**
- A final export needs a **human approval**: a decision bound to the exact artifact revision and
  readiness it approves. Any later change voids it. The shared export use case checks it,
  whichever interface calls, so a caller cannot pass `actor=user` to skip it.
- **No extra burden on the user** (Vlad, 09-23: no checks that aren't real). In the UI the
  approval *is* the designed 7a export action, with no added dialog. In the CLI, `--final` and
  `done` / `n/a` ask one plain y/N confirmation; a non-interactive call refuses them, and MCP
  does not expose them.
- `AGENTS.md` forbids agents from making them. An agent determined to fake a terminal could, which
  is why this is a policy.
- While Vlad is the operator on the Mac, the CLI path stays open. When the auditor takes over, these
  actions become UI-only (decided 09-23).

#### W1 Facturi (`invoices`)

1. Upload a batch of PDFs.
2. Dedupe.
3. Parse: the ported parsers (EDS, MET, ENGIE, ALIVE, OMV Petrom, Next Energy, Getica, Electric
   Planners, Hidroelectrica, Enel/PPC); OCR for scans.
4. **Batch client identity:** Ema proposes the client (CUI/POD/name) once per batch, the user
   confirms, and the CUI/POD mapping is remembered.
5. Review the flagged invoices. Until S9b, an invoice needing review is not exported: the export
   lists it as omitted, as the legacy exporter does (R11). From S9b, a reviewed invoice becomes
   exportable.
6. Export the workbook (the unchanged contract).

Gas and SEE documents are reported as "not supported yet".

#### W2 PIEE (`piee`)

1. Choose client + year.
2. Fill the slots:
   - Anexa 2–3 (year N)
   - Necesar info (year N)
   - optionally the auditor's *Prelucrare date*
3. Import into the dataset: every value becomes a field with its evidence (§5.4). The previous
   years come from last year's job or from her workbook.
4. Review through `core.review`, the same use cases as the audit, from the CLI or the UI:
   conflicts (the „Date anuale" cross-check included), missing fields, uncertain values.
5. Generate a draft from `piee_master.docx` (her latest finished PIEE), following the **PIEE format
   contract (§5.10)**:
   - **Date generale** ← clients + anexa (+ online for what the anexa lacks)
   - **Analiză** ← `consumption_analysis`, written into her existing tables and charts
   - **Audituri și investiții** ← anexa „Audit energetic" + „Solutii EE"
   - **Măsuri** ← „Solutii EE planificate"
   - **Bibliografie** ← anexa title + last audit (year, auditor)
6. Render to PDF, write the TOC page numbers, and run the contract's acceptance checks.
7. Final export when readiness allows it. Output: `.docx` + generated *Prelucrare date* `.xlsx` (her layout, live formulas; a working
   file, not linked from the `.docx`).

#### W3 Audit (`audit`)

A long-lived job that fills her latest finished audit (§5.7) for a new client. The numbers come
from deterministic readers and the shared analysis; everything else is found and written by an
**AI agent** (§5.12), because no fixed rule set can read an arbitrary dossier, research a company
and write her chapters. Each stage is re-runnable on its own, and per section:

| Stage | Does | Output |
|---|---|---|
| 1 Intake | upload in batches; sniff/convert (deterministic); the agent classifies each file against the 13-item checklist + Necesar info + visit material; per-file status | intake records, completeness („lipsesc: 6, 10") |
| 2 Read | deterministic readers for the structured inputs (Necesar info: energy, equipment, fleet, buildings, employees; Anexa 2–3; meter exports) — the numbers | dataset + fields with evidence |
| 3 Fill (agent) | per section of the catalogue, the agent gathers what that part of her audit needs: reads the dossier (text, OCR, vision on photos, schemes and meter displays), uses the dataset, researches online (§5.11), and records each fact with its evidence; what it cannot find is recorded `missing` or `later` | facts (state `extracted` / `enriched`), section statuses |
| 4 Review | the auditor or Vlad confirms or corrects facts and resolves conflicts (`core.review`); confirmed facts carry into next year | decisions |
| 5 Draft (agent) | writes each section as she would, in her patterns, from recorded facts only; ch. 4 from `consumption_analysis` (deterministic, the PIEE's); fixed chapters from the base. Drafting does not wait for review: a fact changed later makes its sections `stale` (§5.9) | section drafts |
| 6 Preview | the filled `.docx` → PDF → a **paged, scrollable viewer** (all pages, like a PDF); per section: jump to its pages | `outputs/draft-<n>.docx` + `.pdf` |
| 7 Export | readiness allows it (every section `done` or `n/a`, none `stale`) → final `.docx` | `outputs/final-<n>.docx` |

**Audit section catalogue: one general structure built from all her audits** (Vlad, 09-23).
Her audits differ by client: AUDIT-01 and AUDIT-02 have no measurement chapter (their „Măsuri" is
ch. 5), while AUDIT-04 and AUDIT-03 have ch. 5 „Bilanțurile energetice", with both an electrical
part (bilanț, fișă, rezultate, concluzii) and a thermal part (bilanț, fișă, rezultate). CLIENT-A3
2022 (the old template) has electrical measurements only. So:
- **The catalogue is the union** of every section in her audits (the §5.7 reference set). Each
  section records **when it applies** (e.g. electrical part: meter/analyser photos received;
  thermal part: thermal images received) and **which of her audits supplies its prototype** when
  the base lacks it (ch. 5 comes from AUDIT-03 or AUDIT-04, since AUDIT-01 has none).
- **Nothing is dropped silently.** For every catalogue section the Fill stage records whether it
  applies and why (the input that triggers it, or its absence). A section that applies is filled
  or `later`; one that doesn't is proposed `n/a` with its reason, and only a human confirms `n/a`
  (§5.9), so readiness lists every section until each has an answer. Chapters and captions renumber
  when a chapter is absent.
- **Something none of her audits has** (a client needing an analysis she has never written) is
  never invented: the agent raises it as a review item for the auditor, who decides whether it
  becomes a new catalogue section.

The catalogue (each section's kind and sources):

| Section | Kind | Sources |
|---|---|---|
| 1 Scop, obiective, conținut, întocmire, legislație | fixed text | template (client name substituted) |
| 2.1 Date generale (+ manager energetic) | data + conditional text | clients, Anexa 2–3, questionnaire; ≥/< 1000 tep rule |
| 2.2 Localizarea companiei | narrative + map | online (locality/county, population), OSM map or `later: map` |
| 2.3 Istoria companiei | narrative | online (company site, press) + client |
| 3.1 Fluxuri tehnologice / secții + dotări | narrative + tables + figures | dossier (flows, permit, schemes) + visit photos + equipment enrichment |
| 3.2 Utilități (apă, energie electrică, gaz / termică, carburanți, aer comprimat…) | narrative + tables | dossier + questionnaire + visit |
| 3.3 Iluminat · 3.4 Parc auto · 3.5 Contorizare · 3.6 Automatizare | data + narrative | questionnaire (fleet, buildings) + visit |
| 4.x Analiza consumurilor | data blocks | `consumption_analysis` |
| 5 Bilanțuri energetice (electro + termic) | method text + results + narrative | visit material: **photos of meter/analyser displays grouped by panel** (e.g. Siemens PAC3220: THD, voltages, currents, cos φ) and FLIR images → a vision model reads the values into `MeasurementFacts` (the photo is the source; the auditor confirms) → her measurement-sheet pattern (figure + values + interpretation vs. norms). `later` until received |
| 6.1 Indicatori financiari · 6.2 Măsuri generale | fixed/parameterised text | template + calc |
| 6.3 Măsuri specifice · 6.4 Sinteza | auditor measures form + table + deterministic tep, CO₂ and TRB | labelled „Măsuri propuse” form with cell evidence; per-measure narrative remains a marked gap that blocks final export until a later draft-agent slice |
| 7 Surse de finanțare | fixed text | template |

**Draft rules for AI narrative:**
- Only recorded facts may appear. A missing fact produces a `missing` status (and a marker in the
  draft), never invented text. What the checks can and cannot establish is in §5.12; flagged or
  uncited sentences go to review, never silently into the document.
- The text reads as hers: no mention of AI, no disclaimers, no notes on how it was produced (R2);
  a check refuses a draft that has any.
- Her patterns: announce → figure/table → observe → enumerate; process stages with their
  purpose; indicator explanations; equipment explained for a non-technical reader.
- Regenerating a section never touches the others.
- **No in-app document editing** (out of scope). Corrections are made by editing **facts** and
  regenerating; final polishing happens in Word after export.

#### W4 Raportare manager energetic (`reporting`)

1. Choose years + clients (defaults: all clients with an annex).
2. Read each Anexa 2–3 (Date generale + Date lunare + Solutii EE).
3. Split measures by commissioning year (col. C).
4. Output: her workbook, one sheet per year, + a Control sheet (source file, sha256, cells used)
   + an Exceptions sheet (missing measures or costs).

### 5.10 PIEE format contract

Settled 2026-09-19 on the CLIENT-P1 PIEE. W2 must reproduce it deterministically, with no LLM.

- **Golden:** `$EMA_REFERENCE/piee/cases/piee-case-a/generated/Program de îmbunătățire a eficienței
  energetice CLIENT-P1 SA_2026.docx`, prepared for the auditor on 2026-09-19. **Approved by
  the auditor** (reported 09-23), pies included: evidence level 4 (§5.16). The format is proven; S8
  makes the system produce it for any client.
- **Reference implementation:** `…/piee-case-a/working/CLIENT-I5-format-generator/`
  (`data_tg.py`, `build_tg.py`, `charts_tg.py`). These are one-off scripts, not product code. S8
  re-implements them inside `piee` + the document engine and must reproduce the golden.

**Base**
- The base is **the auditor's latest finished PIEE, cloned** (today `MODEL_2026.docx`, CLIENT-I5).
  Only client content changes.
- These are never touched: styles, fonts, heading numbering, header („ANTET"), the page-number
  footer, caption styles, table styles, and the signature/stamp images.
- Text is replaced **inside the existing runs**, so mixed formatting survives. Never rebuild a
  paragraph.

**Anchor map (the replacement contract)**
- Every element of the base is classified **fixed** or **variable** in an anchor map versioned
  with it: paragraphs, table cells and row groups, charts (series, caches, embedded workbook),
  pictures, headers and footers, text boxes, hyperlinks, bookmarks and document properties.
  Paragraph/cell/chart-part granularity; runs are an implementation detail.
- **Anchors are found by id, never by their words or position.** When a base version's map is
  built, each variable anchor is stamped with a hidden bookmark (`_ema_<slot>`; Word hides
  bookmarks starting with `_`). The engine finds anchors only by those bookmarks: not by
  paragraph index (the one-off CLIENT-P1 script's `P(237)`, which breaks as soon as a paragraph
  moves), and not by matching the text in them. The `_ema_` bookmarks are stripped from the
  exported file. Words are used only where nothing else is stable: once, to build a base's map,
  checked by a human preview (§10.6); in the leftover check; and in the readers of client files,
  where labels are the only stable handle (§5.5, with aliases and a loud failure when a label is
  missing or ambiguous).
- The engine records every variable anchor it writes or removes. **A variable anchor left
  untouched blocks the final export** (§5.9); a draft lists it. This is what catches a stale
  number: no figure survives from the base unless its anchor is fixed.
- An element the map does not classify fails the **base's** validation, not a client's export: a
  new base is not used until its map is complete and the auditor has seen its preview (§10.6).
- **Leftover check over the whole package**, not only the body: every XML part (headers, footers,
  footnotes, text boxes, chart XML, relationship targets, alt text, comments,
  `docProps/core.xml` + `app.xml`) and every embedded workbook. The denylist is the base client's
  identity: name and short forms, CUI, registration no., address, phone, website, contact person,
  product words.
- Negative fixtures (unit): a base-client string planted in a header, a chart cache, an embedded
  workbook cell, a hyperlink target, alt text and `docProps` each fail the check.
- The engine counts as reusable only once both S8 cases pass: CLIENT-P1 (the golden) and piee-case-b.

**Client identity**
- The client name is replaced everywhere: body, captions, tables, **TOC hyperlink text**,
  signature table.
- **Date generale** comes from Anexa 2–3: address, CUI, capital (state/private split), phone/fax,
  website (text **and** hyperlink target), CAEN code + description.
- The Registrul Comerțului number comes from an online source when the annex lacks it (R5).
- The **first-page footer** holds the client's address and phone in her English pattern
  (`<no> <street>, <postcode> <city>, <county> County` / `Phone: …; Fax: …`).
- Signature table:
  - client name
  - `Director societate xxxxx` kept as her yellow placeholder
  - contact person from the inputs, otherwise a red `n.d.`
  - `DATA TRIMITERII` = the generation date

**Numbers and wording**
- Period = the last 3 years.
- **Production unit = the client's own unit** (CLIENT-P1: mii MWh of gas transported). Specific
  consumption = tep per that unit. Units in text, table captions and axis titles all follow it.
- Factors are those of her workbook: electricity and gas 0.086 tep/MWh; motorină 1.015 tep/t;
  benzină 1.05 tep/t. CO₂: 0.226 / 0.1787 / 3.259 / 3.068.
- **Cross-check: total tep must equal Anexa 2–3 „Date anuale".** A mismatch is a conflict, not a
  warning.
- Number formats (Romanian, `1.234,56`):
  - presentation follows her prototype table by table (its `Num.grouping`): her AUDIT-01 tables write numbers ≥ 1000
    without a thousands separator. `1.234,56` is the default only where the prototype does not say.
  - monthly tables and annual lines: 2 decimals
  - specific consumption and intensity: 4 decimals
  - CO₂ table: integers
- Trend word from the least-squares slope: `creștere` if > 0, otherwise `scădere`. A flat series
  is phrased as „s-a menținut constantă".
- Values are presented as filed, with no smoothing. Example: the piee-case-a gas jump.

**Sections, missing data, numbering**
- A carrier that **the client doesn't have** is removed: its series, and its words in the text
  (e.g. propane/GPL).
- A carrier **with no data** keeps its heading plus one red line: „Date indisponibile pentru
  perioada de analiză AAAA – AAAA." Both water types (potable, industrial) are always present. The
  same applies to their specific-consumption subsection.
- **Missing monthly values** are shown as red `n.d.` table cells.
- A **year with no monthly data**: its figure and that figure's intro, caption and observation are
  removed, replaced by one red line („Anul 2025: date lunare indisponibile.").
- Figures and tables are **renumbered sequentially** after removals or additions, and every
  „figura/tabelul numărul X" reference is updated.
- **TOC:**
  - Edit the entries: client name, added or removed headings, their numbers.
  - Then refresh **page numbers only** (§5.7: Word's own update, on the Mac and on Windows).
  - Never regenerate the whole TOC: that resets her compact entry spacing.
  - Never rely on update-fields-on-open, which shows the client a dialog.
- **Variable-length tables** (audit measures, implemented measures, planned measures):
  - rows are cloned from her first data row
  - values come as filed from the annex sheets („Audit energetic", „Solutii EE",
    „Solutii EE planificate")
  - payback = cost ÷ cost savings
  - anything the annex doesn't provide (e.g. t CO₂ per audit measure) is a red `n.d.`
- The planned-measures period comes from the annex terms (e.g. „2026 – 2029").
- Audit text and bibliography come from the annex: last audit year, auditor, ISO 50001
  certification.

**Charts (R4b + R4d)**
- **Keep her 31 native bar charts.** For each one:
  - rewrite the value and series-name caches
  - drop the series of absent carriers
  - **replace the external OneDrive link with an embedded workbook** that reproduces the
    referenced sheet/cells, so „Edit Data" works (`autoUpdate 0` kept)
  - remove the chart parts of removed figures from the package
- Value axes:
  - drop fixed `majorUnit`/`minorUnit`/`max`
  - `min 0` always
  - axis titles are auto-placed
  - where the labels are much wider than in her data (≥ 5–6 digits), the plot area is also
    auto-laid out, so titles don't overlap the labels
- **Pies:** her pasted pie pictures become **native 3D pie charts** of the same size. the auditor
  approved the CLIENT-P1 pies and wants them **exactly like that** (09-23), so this spec is fixed:
  - common style:
    - colours `4F81BD` / `C0504D` / `9BBB59`
    - Times New Roman
    - legend on the right
    - labels `0.00%`
    - `rotX 30`, `perspective 30`
  - PV share: 10 pt text, no label fill, border `D9D9D9`
  - energy mix: 8 pt text, labels on `D9D9D9` boxes, explosion 20, border `868686`

**Acceptance for every generated PIEE**
- Word opens it with no repair prompt.
- Zero external relationships other than hyperlinks.
- One embedded workbook per chart.
- No string from the base client remains anywhere in the package (the leftover check above), and
  no variable anchor is untouched.
- A page-by-page render is compared with her template: same styles and visuals, content changed.

### 5.11 Online research (R5, R6)

- **The agent is free to research** (decided 09-23): it searches, follows links, reads what it
  finds, and decides for itself whether a source is legitimate. There is no list of allowed sites
  or fields. The order below is guidance in its instructions, not a gate:
  1. official registries (ANAF CUI web service, ONRC data)
  2. the company's own website
  3. equipment manufacturers' pages / datasheets
  4. reputable encyclopaedic sources (locality/county data)
  5. the general web
- **Supplied first (R5):** a value the client supplied stays active; a differing online value is
  shown as an alternative for review, never swapped in.
- **What leaves the machine, enforced by code.** Search queries are the agent's own free text
  (the decision above), so the boundary is checked on every outbound query and URL, not asked of
  the agent:
  - code builds the job's **private values** from its facts — figures from the dataset and the
    documents (consumptions, costs, production), contact data (e-mails, phones, people's names),
    account and contract numbers — and refuses any query or URL containing one
  - queries are length-capped, so no passage of a document can be pasted into a search
  - every outbound query and URL is logged in the job's log
  - **client documents never go to search.** They go only to the configured LLM provider (R15).
- **Traceable, whatever the source.** Every online fact stores URL, retrieval date, the quoted
  snippet and the agent's one-line reason for trusting the source; it is shown with a „sursă"
  chip. Every fetched page is kept as a dated snapshot (the evidence's `snapshot_sha`), so the
  snippet shows what was read even after the site changes. A quote the agent reports must appear
  verbatim in its snapshot, otherwise the value is not recorded: this checks that the fact was
  read, not where it came from.
- **Images:** a manufacturer or open-licence source with attribution, otherwise a `later` item
  (a visit photo).
- Results are cached per client and per equipment model, so the same model is looked up only once.
- **Safety rails that do not limit research:**
  - the fetcher reaches only the public internet (`http(s)`, public addresses, re-checked on every
    redirect; size, type and time limits), so a link can never reach the auditor's network or Ema's
    own API; S13 tests a local address and a redirect to one
  - web text is treated as hostile: it reaches the model delimited as untrusted data, and what a
    page could make the agent do is **contained by its tools**, not prevented by the prompt. The
    tools are scoped per stage (Fill: read, search, fetch, record a fact; Draft: read facts, write
    a draft; no web in Draft), and every tool is bound to the current job by code, so no tool can
    write outside it
  - S13 tests a page that tries to make the agent search with private data and write outside the
    job: both are refused and logged

### 5.12 LLM layer

- **Providers:** Gemini (default) and OpenAI (optional). **No automatic routing.** The user picks
  the provider in Settings, and can switch at any time.
- **Models:** each provider shows a **short curated list**: a standard default plus one stronger
  option. Nothing overkill (slow/expensive) or underpowered. The list lives in a config file
  shipped with each release and is reviewed per release (model IDs change often; none are
  hard-coded in the code).
- **Vision** (meter photos, FLIR overlays) uses the same selected provider/model. The curated list
  only offers models with vision.
- **Structured output only:** pydantic schema in, validated JSON out. It retries once on a schema
  failure, then records a visible error.
- **The agent loop** (`run_agent`, the audit's Fill and Draft stages, intake classification): the
  selected provider's tool calling in our own small loop, no agent framework. Its tools are Ema's
  use cases: read a file (text, OCR, page image), read the dataset, search, fetch, look up a
  registry, record a fact, mark a field missing or a section `later`, write a section draft.
  - The agent has freedom in *how* it works (what to read, where to search, what to trust); the
    product's rules are enforced by the tools, not by trust: a fact enters only through
    record-fact with evidence, and for a text source its quote must be found verbatim in the file
    text or snapshot.
  - **Vision readings** (meter displays, FLIR overlays) have no text to match. They are recorded
    with their photo region and stay `needs confirmation` — never auto-accepted, not even by
    „Accept exact matches automatically" — until a human checks the value against the region.
  - **What code can check in a draft, and what it cannot.** Checked mechanically: every number
    is a fact reference; every paragraph lists the fact ids it rests on, and each must exist;
    names (client, people, equipment, places) must match facts; no AI mention. Not provable by
    code: whether a sentence is *true to* its facts — a qualitative claim („echipamente moderne,
    eficiente"), an overstatement. For those, a second model pass flags sentences their cited
    facts do not support, and the flags plus any uncited sentence go to review. The result is
    reported as **traceability coverage**, never as proof of truth.
  - A per-section step limit stops a runaway loop as a visible, resumable error; costs are
    logged, with no cap (§4).
- Prompts are versioned in code (`audit/prompts/…`), with style-guide excerpts and worked
  examples from all her 2026 audits (§5.7 reference set).
- Every call is logged: provider, model, prompt version, tokens, estimated cost, duration. The job
  shows its total AI cost. No cap for now. No keys in logs.
- **Offline or provider error:** deterministic stages keep working; AI stages show a clear
  "waiting for AI" state and can be resumed.
- **Privacy note (Gemini free tier):** under Google's terms, content sent through the **unpaid**
  Gemini API may be used to improve Google's products and may be seen by human reviewers.
  **Paid** (billing-enabled) usage is not used that way. Client documents should go only through
  a billing-enabled key, or through OpenAI's API, whose data isn't used for training by default.
  The free tier is fine for development with non-confidential data. Decide before real client use
  (§10.7).
- Tests use recorded responses (no network in CI).

### 5.13 Interfaces

**HTTP API** (FastAPI; the OpenAPI schema is the frontend contract):

```
GET/POST   /clients                      GET/PATCH /clients/{id}
POST       /clients/{id}/files           GET /clients/{id}/files/{sha}/versions
POST       /jobs                         {type: invoices|piee|audit|reporting, client?, year?}
GET        /jobs/{id}                    GET /jobs/{id}/events   (server-sent progress)
PUT        /jobs/{id}/slots/{slot}       DELETE /jobs/{id}/slots/{slot}/versions/{v}
POST       /jobs/{id}/stages/{stage}     POST /jobs/{id}/cancel
POST       /jobs/{id}/stages/measures    (audit: deterministic form read and ch. 6 plan)
GET        /audit/forms/masuri-propuse.xlsx  (blank „Măsuri propuse” workbook)
GET/PATCH  /jobs/{id}/facts              GET /jobs/{id}/conflicts  POST /jobs/{id}/conflicts/{c}
GET/PATCH  /jobs/{id}/sections           POST /jobs/{id}/sections/{s}/draft
GET        /jobs/{id}/preview.pdf        GET /jobs/{id}/outputs/{name}
GET/PUT    /settings                     (providers + keys → keyring, workspace path)

added for the design handoff (§5.18):
GET        /jobs/{id}/fields             ?status=pending|uncertain|accepted   (3c, 3f, 3g rows)
POST       /jobs/{id}/fields/{f}/decide  {action, value?, onRevision}   POST /jobs/{id}/fields/accept-batch
GET        /jobs/{id}/log                POST /jobs/{id}/log/{entry}/undo     (Jurnal, R19)
GET        /evidence/{id}/snippet.png    ?highlight=1  (page crop, R18)
GET        /evidence/{id}/page.png       GET /evidence/{id}/quote
GET        /jobs/{id}/export/checks      POST /jobs/{id}/export               (7a)
POST       /settings/providers/{p}/test  (the „verificată acum 2 h" state in 3i)
```

**CLI** (Typer; the same use cases; used by agents and golden tests):

```
ema serve
ema invoices extract <folder> --client <cui>
ema piee generate --client <cui> --year 2025 --anexa <file> --necesar <file> [--prelucrare <file>]
                                          (job + slots + import + draft in one call; never a final)
ema job fields <job> [--status pending|conflict|missing]
ema job decide <job> <field> accept | correct <value> | reject | choose <alternative>
ema job log <job> ; ema job undo <job> <entry>
ema job checks <job> ; ema job export <job> [--final]    (--final: one y/N human confirmation)
ema reporting generate --years 2023-2025
ema audit new --client <cui> --year 2026 ; ema audit add <job> <files…> ; ema audit run <job> <stage>
ema audit status <job>
ema audit draft <job> <section> [--draft-recording <file> --support-recording <file>]   (replay only)
ema audit measures <job> ; ema audit measures-form <dest>
ema mcp [--import-root <dir>]…                                                             (stdio MCP server)
```

**MCP** (S19; `ema mcp`, stdio, server `ema`, SDK `mcp==1.30.0`):
- eleven tools over the CLI's use cases: `workspace_info`, `job_list`, `job_status`, `job_fields`, `job_decide`,
  `job_log`, `job_checks`, `audit_sections`, `audit_draft_section`, `audit_measures`, `piee_generate`
- one workspace per server, chosen as the CLI chooses it; input files only from `<workspace>/imports/` or an
  `--import-root`; nothing is written outside the workspace
- every call acts as `agent`: no final export, approval, `done`/`n/a`, undo or delete (R14)
- audit drafting replays recorded responses; without recordings it answers `ai_client_disabled` (live AI not approved)

### 5.14 Errors, logging, observability

- **Typed errors:** `EmaError(code, user_message_ro, detail)`. The API returns problem+json.
  The UI shows the Romanian message; the detail and traceback go to `log.jsonl`.
- **Nothing is swallowed.** A worker's stderr is part of the log. A failed file or section
  shows its own error inline.
- The job log is the single place to debug. A "copy diagnostics" button in the UI zips a
  redacted log + a snapshot of the job's rows (§5.15).

### 5.15 Security and privacy

- **Local-first:** client data stays in the workspace. Data leaves the machine only via (a) LLM
  calls to the configured provider and (b) enrichment searches with public identifiers.
- Keys live in the OS keyring. Never in files, logs or the frontend.
- **The API binds to `127.0.0.1` and checks every route** — JSON, SSE, the PDF preview, snippet
  images, downloads:
  - `Host` must be `127.0.0.1:<port>` (stops DNS rebinding); `Origin`, when present, must be the
    app's own. No CORS headers at all.
  - The window opens `/` with a one-time launch code in the URL **fragment**. A fragment is never
    sent in an HTTP request, so the code never reaches the server's request log. The page posts it
    to `/session` and gets a host-only `HttpOnly; SameSite=Strict` session cookie (no `Secure`
    flag: the origin is plain `http://127.0.0.1:<port>`); the code is then spent. Images, pdf.js
    and SSE then work with no token in any request URL. `ema serve` prints the same kind of link
    for the dev browser (through the Vite proxy).
  - No token or code appears in a request URL, a log or the diagnostics.
- **Diagnostics are redacted.** The bundle keeps error codes, stages, timings, traceback frames
  (file, line, function; paths workspace-relative), models and token counts. It drops values,
  quotes, client and file names, exception messages other than `EmaError` codes, and provider
  responses. A unit test plants each of these and checks that none survives. Full logs stay on the
  machine: client material never goes into a bug report.
- Client data never enters git (the reference library is outside the repo; tests read
  `$EMA_REFERENCE`).

### 5.16 Testing strategy

| Layer | What | Where it runs |
|---|---|---|
| Unit | calculations, label-finding, phrase rules, block rendering, parsers on small **synthetic** fixtures | CI + local |
| Golden (real data) | each slice's real case from the reference library: exact numbers, structure (heading tree, tables, captions, chart count), and invoice outputs matching delivered workbooks | local only (`$EMA_REFERENCE`), required before PRs |
| Document checks | generated docx vs the auditor's: heading tree, styles, fonts, table header colour, caption format, native charts present; for PIEEs the §5.10 acceptance list | golden |
| Contract | OpenAPI schema snapshot; import-linter | CI |
| AI | recorded LLM responses; the traceability checks (fact references, cited ids, names, no AI mention) and the support pass (§5.12), reported as coverage; a golden case plants a plausible unsupported qualitative sentence that must be flagged | CI + golden |

**Evidence levels.** Every golden case states its level, and a slice reports the level it
reached, never just „passed":
1. **regression** — equals an output a script or an earlier Ema produced (catches change, not
   correctness)
2. **reference** — numbers and structure equal a document the auditor delivered
3. **Word-visual** — opened and checked in native Word (Word for Mac now, Windows from the port)
4. **approved** — the auditor accepted this output

- The CLIENT-P1 2026 PIEE golden is level 4: the auditor approved it, pies included (09-23). CLIENT-P2
  2025 is level 2.
- S7 is level 2 for presentation only (its datasets come from her audits' own ch. 4 tables).
  Extraction from original inputs is tested in S5, on the cases that have a Necesar info.
- **The CLIENT-A2 final is not a reference** (09-23): it was produced with an agent, not written
  by the auditor. Its inputs (dossier, thermal images, the 36 meter photos) are real test inputs; its
  text and figures are never compared against, mined for phrases, or used as a style guide (R1).
- S14/S15 are compared with her own audits (structure, patterns, level of detail) and reviewed by
  the auditor, not measured for equality. An input the case lacks is reported as not tested, not as
  passed.

### 5.17 Configuration

- One settings file in the workspace + the keyring.
- Settings: workspace path, the active AI provider (Gemini / OpenAI) + one model from the curated
  list (§5.12), OCR language, the Word path, enrichment on/off.

### 5.18 Frontend: the design handoff

`FRONTEND_BRIEF.md` (next to this file) was the input for the design. The **output arrived on
2026-09-21** and replaces it as the frontend reference. The brief stays only as the record of what
was asked for.

**The bundle** — `$EMA_REFERENCE/design/handoff-2026-09-21/` (in the library, never in git):

| File | Role |
|---|---|
| `README.md` | the spec: screens, interactions, state model, the full token table. **Read in full first.** |
| `OVERRIDES.md` | **read with it:** the four data corrections (PIEE source, Facturi carrier, template, draft vs final export), the workflows the design doesn't cover, and the copy rule |
| `EMA Design System.dc.html` | **start here.** 7a export screen · 7b four states · 7c three dialogs · **7d/7e the component sheet** (light/dark) with real values |
| `EMA Hi-Fi.dc.html` | the ten light screens, ids 3b–3j |
| `EMA Dark.dc.html` | dark screens 6a–6c (list, table, document preview) |
| `EMA Overhaul.dc.html` | earlier structural exploration; reasoning only, superseded on visuals |
| `EMA Current UI.dc.html` | the ARGUS UI recreated — the "before" |

- **Authority:** the HTML wins over the README where they disagree; the README wins over this
  section; this section wins on **what the data actually is** (the reconciliation below).
- **Implemented as made** (R20). The screens must look like the HTML — layout, spacing, type,
  colour, components and states — at 1400×900 and scale from 1280×800 up. The HTML is not
  pasted in as code: the token table becomes the theme and the components are rebuilt in our
  stack, and the rebuilt screen is then compared with the HTML screenshot side by side (S17a,
  S17b). A difference is a bug, unless it is one of the data corrections below.
- **Design ids are the shared vocabulary.** Component names and commit messages carry them
  (`FieldReviewRow` "3c", `feat(ui/3c): …`), so any screen can be traced back to the design.

**Three hard rules** (from the README, non-negotiable):
1. **Paper never inverts.** Document previews and scanned pages stay `#fffdf6` with dark ink in
   both themes, and everything nested inside a paper surface keeps the light palette.
2. **Never remove a focus outline** without the replacement ring
   (`0 0 0 2px var(--surface), 0 0 0 4px var(--olive)`; on inputs `0 0 0 3px rgba(olive,.22)`).
3. **Romanian copy is verbatim** — the ş/ţ convention of the files, no translation, no rewording.
   Numbers are Romanian: space thousands, comma decimals, unit after a space (`4 218 kW`).
   The one boundary: a string that **names data the reconciliation corrected** changes with it
   (the complete list is in `OVERRIDES.md`); the designer's commentary at the foot of each option
   is not UI copy. Both sets of replacement strings go to the auditor in the copy pass.

**Look:** warm paper-led desktop. Tokens (light/dark): surface `#f6f2e8`/`#1e1b16`, ink
`#252219`/`#ece5d5`, olive `#4f7015`/`#9bbb52`, amber `#b8751a`/`#d8a24e`, error
`#9e3f1f`/`#e8836a`, violet (second client) `#7a5ea8`/`#a58cd4`, paper `#fffdf6` in both. Geist +
Geist Mono (mono for figures, pages, units, sizes, section keys). Spacing 6/10/14/18/26/34/44,
radii 10/12/14/16–18/21/50%, Lucide-style icons at stroke 1.6–1.8. Full table in the README and in
7d/7e.

**Shell:** sidebar 230 · content · optional activity panel 290; window `border-radius: 18px`;
content column 720px (settings) / 840px (wide). **Designed at 1400×900, built resizable from
1280×800** (decided 09-21) — the columns are fixed and the content column centres, so it scales
without redesign.

#### Screens

| id | Screen | Maps to |
|---|---|---|
| 3e / 6a | **Acasă** | job list + what needs attention (§5.3) |
| 3b / 6b | **Documente** | job slots and versions, intake status per file, OCR, failures (W3 stage 1) |
| 3c / 3h | **Revizuire** | the core screen: one row per proposed value with its source page; accept / correct / leave pending (W3 stage 4, conflicts) |
| 3j | **Structura raportului** | the section board: statuses, subsections, what holds a chapter, week view, client deadline (W3 section statuses, §5.9) |
| 3d | **Raport Word** | generation watched chapter by chapter + the paged preview (W3 stages 5–6) |
| 3f | **Facturi** | the invoice table with per-cell sources and anomalies (W1) |
| 3g / 6c | **PIEE** | the measures table with sources and completeness (W2) |
| 3i | **Setări** | settings, no Save button; Gemini and OpenAI as independent keys, one marked IMPLICIT (§5.12) |
| 7a | **Export** (designed as „Predare") | pre-export checks + the package as a real file list + one primary action |
| 7b | Four shell states | empty · extracting · upload failed · nothing left to review |
| 7c | Three dialogs | delete module · re-run extraction · report already exists |
| 7d / 7e | Component sheet | the implementation reference, light and dark |

**Missing from the handoff, designed before S16a** (full list in `OVERRIDES.md` §5). They are
**drawn by Claude** (decided 09-23) in the handoff's visual direction, from 7d/7e components and
real cases: the data shown, the actions, the states, the copy. They are drawn as HTML screens like
the handoff's, kept beside it in the library (`$EMA_REFERENCE/design/`, never in git, because
they show real client data), and **checked visually**: rendered at 1400×900 in both themes and
compared with the neighbouring handoff screens before they are used. New Romanian copy is marked
**provisional** and goes to the auditor in the copy pass (§10.10). For these screens the drawing is
the reference, and S16a's OpenAPI is derived from them plus the review use cases (S1b):
- **Clienți** (list + client detail with CUI, ANAF data, sites, contacts) — the design addresses
  jobs directly and assumes few clients; the auditor has ~40.
- **Raportare manager energetic** (W4): years + clients → workbook + exceptions.
- **The PIEE's data step:** 3g draws only the measures table, but most of a PIEE is the three-year
  consumption analysis, which needs the 3c treatment before the document is generated.
- **Provenance beyond documents:** online-enriched and calculated facts need their own chip and
  snippet (URL + date + quote instead of a page crop).
- ***Prelucrare date*** as both input and output of a PIEE job.
- **Invoice batch identity** (the client is proposed and confirmed once, before the 3f table).
- The **audit „mai târziu"** reasons are shown well in 3j (visit, measurements) but the explicit
  „nu se aplică" state is not drawn.

#### Design ↔ product reconciliation

The design was drawn from a general reading of the domain. Where it assumes something the real
documents contradict, **the product wins and the visual language stays**:

The corrections below are also written into `OVERRIDES.md` inside the bundle, keyed by design id,
so they are visible to whoever opens the design rather than only here.

| Design assumes | Reality | Resolution |
|---|---|---|
| PIEE = measures taken from **our audit** ch. 6, with an ANRE 1 % target | The PIEE is her 33-page document; its measures come from the client's **Anexa 2–3** („Solutii EE planificate"), and the audit only when EMA did it (§5.10) | Keep the screen (measures table, source chips, per-row missing markers, export bar). Sources = anexa first, audit second. The KPI bar shows production, total tep, CO₂ and **the cross-check against „Date anuale"**, not an ANRE target |
| Facturi = **gas** invoices, „Trimite în audit" | Electricity only (R12); the deliverable is the Excel workbook (R11) | Keep the table, anomaly and source pattern. Primary action „Exportă Excel"; feeding consumption into a job is a later workflow (§10.9) |
| „Şablon: ANRE 2024", nine chapters | Her own master template, seven chapters (§3.2) | The template name is hers; the chapter tree comes from the section catalogue |
| The report exports with `[de completat]` gaps | True for drafts. The **final** audit export needs every section done or n/a (§5.9 readiness); a PIEE marks missing data in red (R4c) | Draft export always allowed with the markers; final export keeps its gate |
| Signature attached on 7a | Her signature and stamp are already images in her template, and the client submits to ANRE | 7a is the **export** screen; no e-signature (decided 09-21) |
| Fixed 1400×900 | Windows, large screen | Designed at 1400×900, resizable from 1280×800 (decided 09-21) |

**What the design adds to the product** (accepted, now requirements R18–R21):
- the **source snippet**: clicking `pag. 44` opens the page crop with the value highlighted, the
  whole sentence, and why Ema is unsure (`F2!C14` for a spreadsheet cell)
- **every accept/reject is reversible and logged** in a per-job „Jurnal", including bulk actions
- **errors are per item**, with the concrete cause and threshold („scan without text at 110 dpi;
  below 200 dpi I cannot extract the figures with confidence") and two exits
- **empty states carry the next step**; the success state pushes to the report structure
- **anomalies are explained, not just flagged** (the October settlement invoice offers „split over
  Jul–Sep" or „leave in October")

#### Frontend state model (proposed 2026-09-21 — for the architecture review)

Derived from the handoff README's prose state model and §5.4. Not yet in the API: after review it
becomes the S16a OpenAPI schema. Enum values are English; Romanian lives only in display copy.

```ts
Field       { id, chapter, key, label, valueType: number|text|year|date|enum, unit?, required,
              value?, revision,
              state: extracted|supplied|enriched|calculated|manual,   // where it came from
              presence: found|not_found|failed,                     // what Ema's search found
              review: pending|accepted|corrected|rejected,          // what the auditor did
              confidence: exact|partial|conflict|none,
              evidence: EvidenceRef[], derivation?: {formula, inputs: FieldId[]},
              alternatives?: {id, value, evidence: EvidenceRef[]}[], chosen?,  // the conflict
              failure?: {cause, threshold?, exits[]}, reason? }
EvidenceRef { id, docId?, kind: pdf_region|pdf_text|cell|docx|photo|url|manual,
              page?, bbox?, cell?, url?, retrievedAt?, quote?, highlight: exact|page|none }
Decision    { id, at, actor: ema|user|agent, fieldId, onRevision,
              action: accept|correct|reject|choose|undo, before, after, batchId?, undoneBy? }
Measure     { id, name, detail?, investmentLei?, savingsMWh?, savingsTep?, paybackYears?,
              term?, responsible?, funding?, origin: anexa|audit|manual, evidence[],
              missing: (keyof Measure)[] }                          // any optional column
SectionNode { id, number, title, status: ready|missing|later|na|drafted|done, stale,
              later?: {reason: visit|measurements|thermography|map|chapter, date?, ref?},
              pages?, children[], note? }
JobDocument { id, name, kind, slot, pages?, sizeBytes, versions[],
              intake: read|reading|failed|needs_ocr|protected,
              failure?: {cause, threshold?, exits[]}, found?: string[] }
Report      { id, version, kind: draft|final, generatedAt, template, editedExternally }
Package     { files: {name, sizeBytes, kind}[], checks: {label, ok, detail}[] }
Settings    { theme, providers: {gemini, openai} each {present, maskedKey?, verifiedAt?},
              defaultProvider, extraction: {ocr, flagUncertain, autoAcceptExact} }
```

Settled in review round 1 (2026-09-23):
- The README's single field `status` is split into **state + presence + review + confidence**:
  facts also arrive from enrichment and calculation, and „not found", „reader failed" and
  „rejected by the auditor" are different things with different next steps.
- Valid combinations: `value` is absent only when `presence` is not `found` and no manual value
  exists; `confidence: conflict` ⇔ two or more `alternatives` and no `chosen`.
- Commands carry the field's `revision`; the Jurnal is typed `Decision`s, so undo and readiness
  read the same records (§5.3).
- `missing[]` on a measure drives the per-row „lipseşte" markers for any optional column.
- Artifacts are addressed by id, never by path. **Outputs are immutable:** the 7c „report
  already exists" dialog creates a new version.
- „Deschide în Word" opens a **working copy** in the job's `edits/`, never the output itself.
  `editedExternally` = the working copy's hash differs from its output's. The UI then offers to
  take the edits in (new copy, marked provisional), which creates a new output revision with
  origin `manual_edit`.
- Final export uses the revision the human approves (§5.9), the newest by default. Regenerating
  after a manual edit makes a new generated revision and says plainly that the manual edits are
  not in it. Copies exported elsewhere are not tracked, and the UI does not claim to know about
  them. S17b tests the 7c flow against an edited working copy.

**Stack:** React + TypeScript strict + Vite; pdf.js for the paged preview; Geist + Geist Mono
bundled (not from Google Fonts); the same format/lint/type gates as the backend.

**Build order (S17a → S17b):** tokens and the component layer from 7d/7e first, then the screens
assembled from those parts.

### 5.19 What happens to the old code

| Source | Decision | Notes |
|---|---|---|
| Legacy `ema-invoice-extractor` (parsers, OCR, exporter/verifier, CLIENT-I7 parsers) | **Port** into `invoices` | the proven contract; add batch identity + the ALIVE OCR fix |
| ARGUS `python/modules/invoice` | Drop | older than the legacy repo |
| PIEE `trends.py`, domain models | **Port and adapt** | into `energy_data` / `consumption_analysis` |
| PIEE readers, `docx_renderer`, `template_preserving`, image charts | **Rewrite** | label-based readers; template engine; native charts |
| CLIENT-P1 one-off scripts (`$EMA_REFERENCE/…/CLIENT-I5-format-generator/`) | **Reference** for S8 | executable form of the §5.10 contract; not product code |
| auditor_prime `romanian_format.py`, `calculation_formulas.py`, `calculation_units.py`, `visual_quality.visual_font` | **Port** (review first) | formatting, formulas, the Romanian-glyph font fallback |
| auditor_prime `definitions/ema_full_energy_audit_v1` | **Reference** | superseded by `audit_master.docx`; mine it for section requirements |
| auditor_prime `enrichment_*`, `official_adapters.py` | **Review** | reuse the ANAF/registry adapters if sound |
| auditor_prime candidates/review/readiness DB, pipeline orchestration, authority, provider lane (~55k LOC) | **Drop** | replaced by facts + section statuses |
| ARGUS Rust core, Tauri layer, `contracts/v1`, `argus_worker` | **Drop** | one Python process instead |
| ARGUS React frontend | **Drop** | Claude Design replaces it; Romanian strings in `copy.ts` can be mined |
| Legacy audit generator | **Drop** (ideas only) | its reference-geometry renderer informs the template engine |
| Festival/campaign docs, evidence files | **Drop** | this document replaces them |

---

## 6. Engineering practice

### 6.1 Repository and locations

```
~/Code/projects/ema/
  code/       repository (private GitHub: Energy-Management-Audit/ema)
  data/       reference library ($EMA_REFERENCE; never in git)
  docs/       project documentation
  tools/      local tools
  artifacts/  generated local artifacts ($EMA_ARTIFACTS; never in git)
```

Repo layout:

```
code/ (repository root)
  AGENTS.md  CLAUDE.md→AGENTS.md  README.md  pyproject.toml  uv.lock
  .pre-commit-config.yaml  .importlinter  .github/workflows/ci.yml
  docs/PLAN.md (this file; §5 is the architecture)  docs/decisions/0001-packaging-and-resources.md
  src/ema/  core/ clients/ energy_data/ consumption_analysis/ invoices/ piee/ reporting/ audit/ api/ cli/ mcp/
  templates/  audit_master.docx  piee_master.docx  energy_manager_report.xlsx  prelucrare_date.xlsx
  tests/unit/  tests/golden/      (golden reads $EMA_REFERENCE; skipped when absent)
  frontend/   packaging/
```

### 6.2 Git workflow

| Branch | Role | From | Into |
|---|---|---|---|
| `prod` | production: what the auditor runs; each merge = a tagged release `v0.x.y` → the installer build | n/a | n/a |
| `dev` | integration; always green | `prod` (once) | `prod` via a release PR |
| `feature/<slice>` | one slice = one branch = one Orca worktree | `dev` | `dev` (PR, squash) |
| `hotfix/<issue>` | urgent production fix | `prod` | `prod` (PR, patch tag) **and** `dev` |
| `release/x.y` | only if releases ever need stabilization | `dev` | `prod` + `dev` |

- **Protection on `prod`/`dev`:** PR + green CI expected; nobody pushes directly, agents included.
  **Not enforced by GitHub** — the org is on the free plan, where branch protection needs a paid
  tier on private repositories. It rests on the convention, on CI being visible on every push and
  PR, and on the review loop in §6.4. Revisit if the org ever upgrades, or if a second engineer
  joins.
- Conventional Commits; features squash-merged.
- SemVer: a release bumps the minor version, a hotfix the patch.
- Golden tests run locally before feature PRs and before every release PR.
- **Orca** runs the agents (09-23; it replaced Conductor). `orca.yaml` (committed) holds the
  worktree setup script: `uv sync --all-groups` and both hook types (`pre-commit install -t
  pre-commit -t pre-push`). Agent instructions
  are **not** repeated there: every agent loads `AGENTS.md` on its own. `EMA_REFERENCE` reaches
  agent terminals from the login shell's environment (`.zshenv`), because the path is this
  machine's. Worktrees start from `dev`.

### 6.3 Coding standards (tools, not prose)

| Standard | Enforced by |
|---|---|
| Formatting | `ruff format`; `prettier` |
| Lint + readability | `ruff check` (pycodestyle, pyflakes, isort, bugbear, pyupgrade, simplify, naming, pylint subset); complexity ≤ 10; limits on statements/branches/args per function |
| Types | `pyright` strict on `src/`; TS `strict` |
| Architecture | `import-linter` contracts (§5.1) |
| File size | a CI check: modules > ~400 lines fail |
| Tests | `pytest` unit (CI) + golden (local) |
| One gate | `scripts/check`, non-mutating: format check, lint, file size on tracked files, pyright, import contracts, non-golden unit tests, and the frontend checks once `frontend/` exists. CI runs exactly it; the pre-push hook runs it; commit hooks may auto-fix. (Today's `.pre-commit-config.yaml` has no tests and fixes instead of checking, so "pre-commit = CI" is not yet true: S1 aligns it and `AGENTS.md`.) |
| Design traceability | frontend commits and component names carry the design id (`feat(ui/3c): …`, `FieldReviewRow` "3c") (§5.18) |

**Where each gate runs:**

| Gate | Runs on | When |
|---|---|---|
| `scripts/check` | Linux CI + every dev machine | every push and PR |
| Golden | a machine with `$EMA_REFERENCE` (Vlad's Mac) | before feature and release PRs |
| Word check: the output opens in Word with no repair prompt, charts open with Edit Data, the TOC numbers are right | Word for Mac now; Vlad's Windows PC from the port | every slice that produces a document; every release |
| Windows build smoke: the frozen one-folder build loads its resources, starts the server, runs one headless job | Windows CI runner | from the port (S18): every push to `dev`, every tag |
| Windows Office checks: Word COM conversion, PDF render, TOC page numbers; the window on WebView2 | Vlad's Windows PC | from the port: every slice that adds Office automation, an external binary or a bundled resource; every release |

**Principles (the one page in `AGENTS.md`):**
- SOLID applied pragmatically:
  - one responsibility per module/function
  - small interfaces only at real boundaries (readers, docx engine, LLM, the Office adapter);
    storage and the runner are module seams, not interfaces, until a second implementation exists
  - composition over inheritance
  - pure calculations
- No abstraction without a second real use.
- One code path per workflow.
- Errors surface with context.
- Domain names in business terms.
- Comments only for the non-obvious *why*.
- **Docs allowed:** README, AGENTS.md, PLAN.md, a few ADRs. No second architecture document: §5
  is it, and AGENTS.md only points there. No evidence files or AI artefacts.

### 6.4 Working model: Claude designs, Codex builds (in Orca)

- **Claude** (product/design lead): this document, slice specs, acceptance, design review of
  diffs. **Codex** (lead engineer): implementation. **The user** arbitrates and merges.
- **Slice spec template** (level 3; lives in the worker's dispatch + the PR description):
  1. **Goal**: 1–2 sentences + the requirement IDs (R…).
  2. **Context**: links to the § of this document.
  3. **Scope**: modules/files to create or change.
  4. **Interfaces**: function signatures, pydantic models, CLI/API shapes.
  5. **Behaviour rules**: edge cases taken from the real files.
  6. **Golden acceptance**: the exact command + expected result on the reference library.
  7. **Unit tests required.**
  8. **Out of scope.**
  9. **Done**: `scripts/check` · the golden command · the Word check where §6.3 asks for it.
- **Bounded review loop** (max 2 rounds each):
  1. Codex critiques the spec before building.
  2. Claude reviews the diff against the spec and the golden output.
  3. Codex adversarial review for engineering risk.
- **How the agents work together in Orca:** Claude is the coordinator, in the primary
  checkout on `dev`; it writes specs, dispatches, reviews and prepares merges, and writes no
  product code. The primary checkout stays on `dev` and is only read and pulled: nobody switches
  branch or commits there. Every change, docs PRs included, is made in its own Orca worktree from
  `dev`, so every open branch shows in Orca. Per slice, from §7:
  1. **Spec** with the template above, narrowing this document; if the plan is wrong, this
     document is fixed first (docs PR).
  2. **Dispatch** one Codex worker (`orca orchestration worker-start`) in a new top-level
     worktree from `dev`, branch `feature/<slice>`, with the spec and a preamble: read
     `AGENTS.md`, critique the spec before coding, Conventional Commits, a PR into `dev` titled
     with the slice id.
  3. **Spec critique** (review round 1): Claude answers, fixes the spec and, if needed, this
     document; then the worker builds.
  4. **Review:** on `worker_done`, Claude runs `scripts/check` and the golden command in the
     worker's worktree and reviews the diff against the spec; findings go back to the same
     worker.
  5. **Adversarial review:** a second Codex worker in the same worktree, engineering risks only.
  6. **PR** description: the spec, the golden output with its evidence level (§5.16), the
     review outcome, and what Vlad checks by hand in Word. No client data, file names only.
  7. **Merge** (Vlad), then the worker is released and §1 is updated.

  At most 3–4 workers at once. Only one worker at a time runs tests that drive Word for Mac
  (§5.5): Claude serializes those golden runs. Two rounds per review step at most, then Vlad
  decides what remains, and the PR description records the outcome.

---

## 7. Roadmap (one slice = one `feature/…` branch = one Orca worktree)

| # | Slice | Golden acceptance (real data) | Depends |
|---|---|---|---|
| S0 | **Spike:** native Word charts (the PIEE edit path and the audit build path) + the TOC page-number cycle, through the Word for Mac adapter (the table/caption blocks are S2) | The three proofs of §5.7, in Word for Mac | none |
| S1 | Repo skeleton: tooling, `scripts/check` = CI, import contracts, `core` workspace/jobs/logging/errors, backup/restore, CLI + API health, the resource path helper | CI green; `ema --help`; job-folder round-trip; backup → restore into a clean folder; an interrupted delete finished on restart | none |
| S1b | Review core: fields + evidence, decisions (Jurnal) + undo, conflicts, readiness contract; the `ema job …` CLI | On a synthetic job: correction → re-run → undo → export; a decision on an old revision refused; an undo superseded by a later decision refused; the same outcomes through the CLI and the use cases the API will call | S1 |
| S2 | `core.office`: label-finding xls/xlsx readers; docx block engine (from S0) | A sample section rendered in her style, checked against her audit | S0, S1 |
| S2b | Legacy intake: type sniffing (incl. HTML-as-`.xls`) + `.doc` conversion with versions | All 12 CLIENT-A1 legacy files usable (5 `.xls` read, 7 `.doc` converted, text verified, converted by Word); a deliberately hung conversion is killed at its timeout and the batch continues | S1 |
| S3 | `energy_data` model, carriers + aliases, factors, `calc` | Reproduces CLIENT-P1 / CLIENT-P2 / CLIENT-A3 *Prelucrare* tep, specific consumption, emissions | S1 |
| S4 | Anexa 2–3 reader | All 38 real annexes parse; exact values on 5 (both form generations, 3 fuel-header variants) | S2, S3 |
| S5 | Necesar info reader (PIEE + audit versions) | CLIENT-P1, CLIENT-A3, CLIENT-A1 parse; monthly values match the sheets | S2, S3 |
| S5b | *Prelucrare date* reader (authoritative) + writer (her layout, formulas) | Reads CLIENT-P1 / CLIENT-A3 / CLIENT-P2; the generated CLIENT-P1 2023–2025 matches the reconstructed one | S3, S5 |
| S6 | Energy-manager report | Reproduces the delivered 2023 (37 companies) and 2025 CLIENT-R1/client-r2 reports | S4 |
| S7 | `consumption_analysis` + phrase bank (from her own audits and PIEEs only) | **AUDIT-01** ch. 4 regenerated from the dataset taken from its own tables (then AUDIT-02 / AUDIT-05): same sections, tables, chart types, phrasing, numbers | S2, S3 |
| S8 | PIEE per the format contract (§5.10): clone her latest PIEE, change client content only | The Word check passes on the generated CLIENT-P1 PIEE. CLIENT-P1 2026 regenerated equals the golden (text, tables, chart caches, embedded workbooks, pies); piee-case-b: numbers match her final. Both run through `core.review` via the CLI: one conflict resolved by a decision, one missing field rendered red, the final export refused until the conflict is resolved | S1b, S4, S5, S5b, S7 |
| S9a | Invoices port (**pypdfium2 + pdfplumber** instead of PyMuPDF), the unchanged workbook contract, `core.pdf` | 29/29 text invoices unchanged vs the legacy output; the 2025 rows equal the delivered CLIENT-I5 and invoice-case-d workbooks | S1 |
| S9b | Batch client identity (confirmed once, through `core.review`) + the CUI/POD memory + the OMV Petrom and ALIVE parsers (ALIVE through OCR, with the ALIVE OCR fix) | CLIENT-I2 24 + ALIVE 13 exportable after one confirmation | S1b, S9a |
| S9a2 | The remaining invoice parser families: Next Energy (e-Factura), Getica, Electric Planners, Hidroelectrica, Enel/PPC | Each family's legacy cases unchanged vs the legacy output (the by-supplier library) | S9a |
| S10 | Audit section catalogue + status transitions (§5.9) + an inventory of the base's repeatable units (processes, equipment tables, measured panels, carriers) | Every heading of every audit in the reference set (AUDIT-01, AUDIT-02, AUDIT-03, AUDIT-04, AUDIT-05; CLIENT-A3 2022 for content) maps to a catalogue section, checked by a script that fails on any unmapped heading; each section has its applicability condition and prototype source; each transition in the table, including `done` → `stale` on a changed input | S1b |
| S10b | Audit base: AUDIT-01 cloned + anchor map + fixed chapters + cloning repeatable units | Ch. 1 and ch. 7 identical to her text for a new client; the base filled for CLIENT-A1 and for CLIENT-A2 (different process counts, carrier mixes and measured panels) keeps her formatting and leaves no untouched anchor | S2, S10 |
| S11 | Audit intake + the agent loop (`run_agent`) + checklist classification by the agent + completeness | CLIENT-A1 dossier fully read; checklist report correct | S2b, S10 |
| S12 | Fill (agent): reading the dossier, record-fact with verified evidence; ch. 2 identity + ch. 4 via S7 | CLIENT-A1 ch. 2 identity + ch. 4 from its Necesar info | S1b, S5, S7, S11 |
| S13 | The agent's online research (§5.11): company, location, map, equipment | CLIENT-A1: CAEN, address, location text, map, 10 equipment entries with sources | S12 |
| S14 | Draft (agent): ch. 2–3 in her patterns + style guide, rendered into the base | CLIENT-A1 and CLIENT-A2 ch. 2–3 drafted from their dossiers + research, compared with her own audits' ch. 2–3 (structure, patterns, detail); CLIENT-A1 reviewed by the auditor; traceability coverage reported; a planted unsupported qualitative sentence is flagged | S10b, S13 |
| S15 | Ch. 5 from visit material (meter-display photos + thermal images → readings via vision → her measurement-sheet model) + ch. 6 measures and financials | CLIENT-A2 ch. 5.1/5.2: the readings from the 36 meter photos match an answer key checked by hand against the photos (not the agent-made final), laid out in her measurement-sheet model, every reading `needs confirmation` until checked; measures table + NPV/payback matching her method | S14 |
| S16a | API contract (OpenAPI) + mock server. **Frozen:** the job, slot, field, evidence, decision, Jurnal, section and readiness endpoints, backed by S1b/S10. **Provisional** (marked `x-provisional`): the workflow-specific ones (PIEE generation, invoices, reporting, audit stages, export packages), drawn from the screens | Every screen in §5.18 maps to endpoints; every frozen endpoint calls an existing use case; frontend runs on mocks; the two-process dev loop (Vite proxy + `ema serve`) passes the §5.15 session checks | S1b, S10 |
| S16 | Full HTTP API + SSE progress; every provisional endpoint reconciled with its slice (S6, S8, S9, S12), with a versioned contract diff | OpenAPI covers every CLI use case, nothing left `x-provisional`; the S1b scenario and a real PIEE journey pass through the API | S6, S8, S9, S12 |
| S17a | Design system: tokens (both themes) + the component layer from 7d/7e | The component sheet reproduced in light and dark and matching 7d/7e screenshots side by side; focus rings, row/button states, toggles match; paper stays paper in dark | S16a |
| S17b | Screens assembled from those components (3b–3j, 6a–6c, 7a–7c) + the screens contracted before S16a. **The PIEE journey (data review → draft → export) first, shown to the auditor before the rest** | the auditor's journeys work end-to-end on the real API; each screen matches its handoff (or Claude-drawn) screenshot side by side at 1400×900, and holds at 1280×800 | S16, S17a |
| S18 | **Windows port:** frozen one-folder build + its smoke job in CI, Word in the Office adapter (conversion, PDF render, TOC page numbers), the Windows Office checks on Vlad's PC, installer (Inno Setup), in-app update check | Installs per-user without admin rights; a PIEE and an audit job give the same outputs as on the Mac; a hung Word conversion is killed without touching an open Word; detects a newer release | S17b |
| S19 | MCP server | An agent generates a PIEE and drafts an audit section headlessly | S16 |

**Parallel tracks:**
- S9a at any time after S1; S9b after S1b; S9a2 after S9a (S9 was split 09-23, re-split 09-24, so each PR can be reviewed)
- S3 alongside S0/S2
- S6 right after S4 (an early win for the auditor)
- design handoff in hand → the missing screens drawn and checked → S16a → S17a → S17b

---

## 8. Moving from the old world to the new

**Done on 2026-09-21:**
1. ✅ The library moved to `~/Code/projects/ema/data/` (`$EMA_REFERENCE`); the scripts inside
   it were repointed and still reproduce the CLIENT-P1 PIEE.
2. ✅ The campaign is archived at `~/Code/projects/_archive/ema-campaign/`, with its final state
   committed. ARGUS and the three legacy repos kept their `.git`, so they stay readable for
   porting; their uncommitted work was committed locally and not pushed.
3. ✅ ARGUS build output (20 GB `target/`, `node_modules`, `artifacts`) moved to
   `~/.Trash/ema-cleanup-2026-09-21/`. The archive is 4.7 GB.
4. ✅ `~/Code/projects/ema/` is the new repository, pushed to the private
   `Energy-Management-Audit/ema` with `prod` and `dev` (default `dev`), CI green on both. It holds
   the skeleton only: gates, import contracts, empty packages, this plan, `AGENTS.md` and ADR
   0001. `FRONTEND_BRIEF-2026-09-19.md` moved into the library beside the handoff.

**Remaining:**
5. Codex workers build the slices in Orca (§6.4), starting with S0, S1 and S3.
6. Port the code per §5.19 in its slices (always from the archive, never by wholesale copy). The
   legacy repos are retired only once their parts are ported (S3, S7, S9), not before.
7. After Ema's first real delivered job:
   - archive the legacy GitHub repos (read-only)
   - delete `_archive/ema-campaign/` (this also deletes ARGUS, as accepted)
   - remove the old app from the auditor's PC (if installed)

Security to-dos: rotate the Gemini key and change the shared mailbox password, before real client
use; not urgent while the app is in development (Vlad, 09-23).

---

## 9. Open questions and what we need

**From Vlad**
1. ~~pywebview~~, ~~repo layout/name~~ and ~~the §8 swap~~: done.
2. ~~Share the Claude Design output~~: received 09-21 (§5.18).
3. ~~LibreOffice on the auditor's PC~~: dropped (09-23); Word is required.
4. The topics in §10.
5. ~~The Windows + Word machine~~: Vlad's Windows PC, from the Windows port (S18); until then
   the app is built and run on the Mac (09-23).
6. ~~A final PIEE whose TOC page numbers were not set by Word~~: Word sets them, on the Mac
   through AppleScript (proven 09-23, §5.7).
7. ~~Who draws the screens the handoff lacks~~: Claude, in the handoff's direction, checked
   visually (09-23, §5.18).
8. ~~the auditor's verdict on the CLIENT-P1 PIEE~~: approved, pies included (09-23).

**From the auditor**, ranked by how much they unblock:
1. ~~CLIENT-A2 inputs~~ **resolved (2026-09-19):**
   - The `.rar` from the 14 Aug email = exactly the 4 received files (hashes verified).
   - The final's ch. 4 contains the full monthly dataset 2023–2025 (20 tables: production,
     electricity, gas, fuels, water), so the dataset can be rebuilt from her own tables.
   - Original photos and FLIR files can't be provided. That's fine: the final's 83 embedded images
     and the WhatsApp thermal images stand in for them.
   - **Electrical measurements added (2026-09-19):** `electro.rar` holds 36 Siemens PAC3220 meter
     display photos across 4 panels (THD, voltages, currents…), which are the inputs of ch. 5.1.
     It also holds the auditor's model for „Fișa de măsurători electroenergetice", written from
     analyser screen photos. Together with the 26 thermal images (ch. 5.2), CLIENT-A2 now covers
     every chapter.
   - Nice to have only: CLIENT-A2's Necesar info / *Prelucrare date*.
2. **Which finished audit is her current base.** Provisional: AUDIT-01 2026, her latest own audit
   in the library (§5.7); work does not wait for the answer. A blank template is no longer needed.
3. Confirm that her *Prelucrare date* values are always taken as-is from the client's Necesar
   info, and which one wins if they differ (the proposed order is in §5.6; her answer changes only
   that order).
4. Anexa 2–3 + Necesar info for **CLIENT-I5 2025** (so the CLIENT-I5 PIEE has a matching input set).
5. Invoice examples for **Next Energy, Getica, Electric Planners, Hidroelectrica, Enel/PPC**, and
   the CLIENT-I7 / CLIENT-I3 / invoice-case-d 2023–2024 PDFs if still available.
6. How she wants SEE re-invoicing documents represented later (ignore vs cost lines).

---

## 10. Still to settle before slice specs (discuss, then challenge with the Codex agent)

Settled on 2026-09-19 (see §4): two machines (1), Windows distribution (2), PDF licence (4),
document preview (5), AI provider and models (7), telemetry (8). The remaining points (3, 6, the
open part of 7) have a recommended default, which applies unless the user or the Codex review
objects.

1. **Two machines:** separate workspaces; export = the deliverable files, import = loading input
   data; no job transfer (§5.3). A hosted backend later.
2. **Windows distribution:** an unsigned installer + an in-app update check against the latest
   GitHub release (release notes + download link); SmartScreen warning accepted.
3. **Backup and protection of client data on the auditor's PC.** *Default:*
   - the workspace stays on the local disk
   - a weekly **"Backup" button + reminder** that writes the §5.3 snapshot to a folder she
     chooses (e.g. OneDrive or an external disk); never a live-synced SQLite
   - `ema backup` / `ema restore` exist from S1; the button and reminder come with S17b
   - recommend BitLocker disk encryption
4. **PDF licence:** pypdfium2 + pdfplumber replace PyMuPDF in S9 (PyMuPDF is AGPL-3.0).
5. **Document preview (decided 09-19):** a **paged, scrollable preview of the whole document**, like
   a PDF viewer (all pages, zoom, jump to a section's pages). **No editing engine** (out of scope).
   - Pipeline: the draft `.docx` → PDF via **Word** (AppleScript on the Mac, COM on Windows;
     exact fidelity) → shown with **pdf.js** (Apache-2.0). Without Word there is no preview
     (LibreOffice dropped, 09-23).
   - Plus a "Deschide în Word" button for the real `.docx`.
6. **Template and legislation upkeep.** *Default:*
   - templates are versioned per year
   - the auditor uploads a new template version in Settings, and Ema checks that its slots are intact
   - for the PIEE, her newest finished PIEE becomes the new base. Ema validates its anchor map
     (every element classified, §5.10) and shows her a preview; she promotes it, and only then is
     it used.
   - past jobs keep the template version they used
7. **AI:**
   - manual provider choice (Gemini default, OpenAI optional)
   - curated models (a standard default + one stronger option each)
   - per-job cost display, no cap, no automatic routing (§5.12)
   - **Still open:** use a **billing-enabled Gemini key** for client documents. The free tier's
     content may be used by Google to improve products.
8. **Telemetry: none (decided 09-19).** Diagnostics are exported only on demand (§5.14).
9. **Future workflows** (designed for, not built):
   - Ema filling the official **Anexa 2–3** from the dataset (W6)
   - invoices feeding `energy_data` (monthly consumption from bills)
   - gas invoices and SEE re-invoicing
   - the "Ema" modern house style (R4)
   - a hosted client-upload portal (§2.2)
10. **UI copy is final-for-build, not frozen** (README open question 3). The Romanian strings are
    used verbatim; a review pass with the auditor is expected after S17b, and it only touches strings.
11. **Risk register:**
    - native Word charts (S0 spike; the PIEE path is already proven on Mac, §5.7)
    - Word automation on the Mac (AppleScript): proven for the TOC and PDF on 2026-09-23; an
      earlier hang was the unanswered macOS permission prompt
    - vision reading of meter photos (accuracy + confirmation UX)
    - LLM narrative quality vs the auditor's bar (S14 compared with her own audits, reviewed by her)
    - `.doc` conversion on machines without Office

**Docker: not for the product now.**
- the auditor needs a normal Windows app. Docker Desktop on Windows needs WSL2 and is heavy and
  unfamiliar.
- For development, `uv` already gives reproducible Python environments, and Orca isolates
  work in worktrees.
- Docker becomes worth it for the future hosted backend (10.1) and possibly for CI jobs that need
  Tesseract.
- The code stays container-ready anyway: config via env, no Windows-only code in `core`, and Word
  automation optional.

**An `.exe`: yes.**
- PyInstaller builds `Ema.exe` (one-folder mode: faster start-up, fewer antivirus false
  positives). It bundles Python, the libraries, the built frontend and Tesseract + Romanian
  language data.
- An installer (Inno Setup or NSIS) wraps it into `Ema Setup.exe` with a Start-menu shortcut and
  an uninstaller.
- It uses Edge WebView2, which ships with Windows 10/11.
- The build runs on a Windows GitHub Actions runner for each tag on `prod` (PyInstaller can't
  cross-compile from a Mac).
- Expected size: ~200–350 MB installed.
- Caveats:
  - Without code signing, Windows SmartScreen warns on first run (10.2).
  - A macOS `.app` is possible later, and needs Apple notarization ($99/yr).

---

## Appendix A: Reference library

`~/Code/projects/ema/data/` (`$EMA_REFERENCE`, moved out of the campaign on 2026-09-21):
**250 catalogued files, ~203 MB**
(2026-09-19; 206 files / 161 MB at the Step 1 build). Each file is listed in `catalog.csv` with its
sha256 and original location. Also: `README.md`, `_requirements/auditor-requirements.md`,
`_analysis/01–03`.

| Area | Contents |
|---|---|
| `audit/finished-audits/` | 6 human-written audits: AUDIT-02, AUDIT-01, AUDIT-04, AUDIT-03 (2026), CLIENT-A3 2022 (previous auditor), AUDIT-05 (`Cap 2-3-4 V2.docx`, ch. 1–4) |
| `audit/cases/` | CLIENT-A1 2026 (27 received files); audit-case-b (4 received + the original `.rar`; `visit/thermography/` 26 thermal images; `visit/electrical/tablou-electric-1..4/` 36 PAC3220 display photos + `electro.rar`; the delivered final under `final/`, **produced with an agent: inputs only, never a reference**); audit-case-c (Necesar info + Prelucrare) |
| `piee/` | 36 Anexa 2–3 (2025); CLIENT-I5 PIEE `MODEL_2026` (the auditor; the current PIEE base); CLIENT-P1 case (inputs; reconstructed workbook; `working/CLIENT-I5-format-generator/` scripts; `generated/`: the 18 Sep ARGUS version and **the 19 Sep CLIENT-I5-format golden**); CLIENT-P2 case (inputs, legacy output, final) |
| `invoices/` | 79 real invoices + 6 supporting docs by client (invoice-case-d, CLIENT-I5, CLIENT-I6, CLIENT-I2, CLIENT-I1); accepted workbooks; `by-supplier/` symlinks |
| `energy-manager-reporting/` | the auditor's model + delivered 2023, 2023–2025, 2025 CLIENT-R1/client-r2 reports |
| `design/handoff-2026-09-21/` | the design handoff: README spec, design system (7a–7e), light screens (3b–3j), dark screens (6a–6c), the superseded exploration and the current-UI recreation (§5.18) |

Roles: `received` · `working` · `generated` (never under `audit/`) · `final` · `visit`.
Cleanup: 1.4 GB moved to `~/.Trash/ema-cleanup-2026-09-18/`; the CLIENT-P1 working copies to
`~/.Trash/ema-cleanup-2026-09-19/` (both restorable until the Trash is emptied).
