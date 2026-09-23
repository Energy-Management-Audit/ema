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
| 3. Slice spec | the Conductor workspace prompt + PR description (not a file in the repo) | one slice: exact files, signatures, golden case, out of scope, done commands | Claude writes, Codex reviews |
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
  input→final audit pair**; its ch. 4 tables supply the 2023–2025 dataset (§9).
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
- **Next:**
  1. **Codex review** of the whole architecture, including the frontend contract (bounded, 2
     rounds). The state-model types drafted from the handoff (§5.4) go into that review.
  2. Then the S0 + S1 slice specs.
  3. The repo swap (§8).

---

## 2. Product

### 2.1 What Ema is

- **Ema** is a female-persona AI assistant for **Energy Management & Audit SRL** (the auditor
  AUDITOR, lead auditor / attested energy manager). The name reads as both "Energy Management
  Assistant" and E.M.A.
- She prepares EMA's recurring paperwork so the auditor can focus on analysis, site visits and
  client relationships.
- The UI speaks as Ema, in Romanian. Code, documentation and specs are in English, using the
  Romanian business terms (anexa, tep, Necesar info, Prelucrare date).

### 2.2 Users and scale

- **the auditor** (and later possibly colleagues) on **Windows**, through the UI. She will
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
  final version**.
- R15 AI providers: **OpenAI and Gemini** (allowed to see client documents).
- R16 Maps: a free source first (OpenStreetMap-based, attributed). Otherwise the map is a `later`
  item that the auditor fills from Google Maps.
- R17 Windows first (desktop app), macOS second.

**Interface (from the design handoff, 2026-09-21 — §5.18)**
- R18 **Every proposed value opens its source:** the page crop with the value highlighted, the
  sentence around it, and why it is uncertain; `sheet!cell` for spreadsheets.
- R19 **Every accept, correction and bulk action is reversible and logged** in the job's „Jurnal".
- R20 **The UI follows the handoff:** its tokens, components and ids; paper never inverts; the
  focus ring is never removed without its replacement; Romanian copy verbatim.
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
| 09-19 | `.xls` read directly, `.doc` converted (Word → LibreOffice → flag) |
| 09-19 | Desktop shell: **pywebview + PyInstaller** |
| 09-19 | Repo `~/Code/projects/ema` = `Energy-Management-Audit/ema`; library at `~/Code/projects/ema-reference` |
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
- **Dev loop:** `uv run ema serve` + `npm run dev` in a normal browser. A frozen build only for
  releases.
- **Dependency rules** (enforced by `import-linter` in CI):
  - `interfaces → workflow modules → {consumption_analysis, energy_data, clients} → core`
  - Workflow modules never import each other.
  - `core` imports nothing from Ema.
  - Interfaces contain no business logic.

### 5.2 Modules and what each owns

| Module | Owns | Public entry points (use cases) |
|---|---|---|
| `core.workspace` | workspace folders, content-addressed files, file slots + versions | `add_file`, `set_slot`, `list_versions`, `remove_version` |
| `core.jobs` | job records, stage runs, runner, cancellation, progress events | `create_job`, `run_stage`, `cancel`, `status`, `subscribe` |
| `core.office` | xls/xlsx label-finding readers, file-type sniffing, `.doc` conversion, docx block engine, native charts | `find_label`, `read_block`, `sniff`, `convert_doc`, `render(template, blocks)` |
| `core.pdf` | text extraction, OCR (Tesseract ron+eng) | `text(pdf)`, `ocr(pdf)` |
| `core.llm` | OpenAI + Gemini behind one interface, structured output, cost logging | `complete_json(schema, prompt, context)` |
| `core.web` | allow-listed HTTP fetch + search for enrichment, caching, rate limits | `search`, `fetch` |
| `clients` | client identity (CUI, name, addresses, CAEN, contacts, sites), ANAF lookup | `get_or_create_by_cui`, `refresh_from_registry` |
| `energy_data` | canonical per-client/year dataset, carrier vocabulary, factors, readers, calculations, *Prelucrare* writer | `import_anexa`, `import_necesar_info`, `import_prelucrare`, `build_dataset`, `indicators`, `write_prelucrare` |
| `consumption_analysis` | PIEE / audit-ch. 4 blocks (tables, native charts, phrased commentary) | `blocks(dataset, scope)` |
| `invoices` | the ported extractor, batch identity, workbook export | `extract_batch`, `confirm_client`, `export` |
| `piee` | PIEE job | `generate(client, year)` |
| `reporting` | energy-manager report | `generate(years, clients)` |
| `audit` | the audit job: intake, extract, enrich, facts, sections, draft, render | stage functions (§5.9) |

### 5.3 Storage, jobs and the scaling path

```
<workspace>/                              default %APPDATA%\Ema (Windows), ~/Ema (mac); configurable
  ema.sqlite                              index: clients, files, slots, jobs, stage_runs, sections
  clients/<client-slug>/
    files/<sha256>.<ext>                  every uploaded/converted file once
    jobs/<year>-<type>-<short-id>/
      job.json                            slots → file versions, options, status (relative paths only)
      work/                               dataset.json, facts.json, sections/<id>.json, enrichment/, cache/
      outputs/                            deliverables (.docx / .xlsx), one per run, versioned
      log.jsonl                           steps, warnings, errors + tracebacks, LLM calls (model, tokens, cost)
```

- **File slots with versions.** Each job declares named slots (`anexa_2_3`, `necesar_info`,
  `prelucrare_date`, `dossier[]`, `visit[]`, `invoices[]`). A new upload or conversion adds a
  version; the newest is active; any version can be removed. Nothing is ever "stuck in history".
- **Job lifecycle:** `created → running(stage) → ready | failed | cancelled`. Audit jobs stay
  `open` for weeks, and each stage can be re-run.
  - A stage run is recorded with its inputs (file hashes), duration, outcome, warnings and error.
  - **A failed file or section never fails the whole job.**
- **Runner:** in-process worker threads now (a single user). It sits behind a `JobRunner`
  interface, so a queue with separate workers can replace it for a hosted version without
  touching modules.
- **No local-only assumptions:** relative paths in `job.json`; storage behind `core.workspace`
  (local folder now, S3-compatible later); SQLite now (Postgres possible later); secrets behind an
  interface (OS keyring now, environment/secret store on a server).
- **Backup** = copy the workspace folder. **Delete** = remove the folder + its index rows.
- **Export** = the deliverables the app produces (`outputs/*.docx|.xlsx`), saved wherever the user
  chooses. **Import** = loading input files into a job's slots. There is no job transfer between
  machines: each machine has its own workspace (decided 09-19).

### 5.4 Data model (the key types)

- **`Source`:** where a value came from
  - `{file_sha, locator, method, retrieved_at, quote?}`
  - `locator ∈ {page, bbox?} | sheet!cell | url` — the bbox is what makes the snippet crop
    possible (R18)
  - `method ∈ questionnaire | anexa | prelucrare | invoice | online | manual | calc`
- **`Value[T]`:** `{value, unit?, source, state, review, history[]}`
  - `state` = where it came from: `supplied | extracted | enriched | calculated | manual`
  - `review` = what the auditor did with it: `pending | accepted | corrected | rejected | missing`
    (`missing` = not found anywhere; the UI asks for it)
  - `history[]` = `{at, actor (ema|user), from, to, action, batch_id?}` — every entry is
    undoable, including bulk accepts (R19)
  - Two conflicting values are both kept, and the job shows a conflict until one is chosen.
    „Accept exact matches automatically" (3i) may pre-accept identical values; they stay in the
    log and can be undone.
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
- **`SectionStatus`:**
  - `ready | missing(facts) | later(visit | thermography | electrical | map) | n/a | done`
  - plus `stale` (inputs changed since the draft)

### 5.5 Readers and legacy formats

- **Label-based readers:** find a label (case/diacritics-insensitive, alias list), then read
  relative to it. No fixed cell address anywhere.
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
    1. Word automation (Windows COM, hidden, one at a time, hard timeout)
    2. otherwise LibreOffice headless
    3. otherwise flagged *needs conversion* (the rest continues)
  - The converted `.docx` is a new version (`converted_from`), and word/table counts are checked
    against the original.

### 5.6 Calculations and factors

- Pure functions over `EnergyDataset`, no I/O.
- **Factors** (tep/MWh conversions, e.g. 1 MWh = 0.086 tep; fuel t → tep; CO₂ factors) are
  versioned by year with their source (from the auditor's „Principali factori", „Factori de
  conversie in MWh" (Eurostat) and „impact de mediu" sheets). A factor change never rewrites a
  past job.
- **Verified** by reproducing her *Prelucrare date* numbers (CLIENT-P1, CLIENT-P2, CLIENT-A3).

### 5.7 Document engine (template + slots + blocks)

- **Templates** in `templates/`, built from the auditor's real documents:
  - `audit_master.docx`: her full chapter tree, **with all client data removed**; fixed ch. 1 and
    ch. 7 text; header, styles, green table style, captions, TOC field
  - `piee_master.docx`: **her latest finished PIEE kept verbatim** (today the CLIENT-I5
    `MODEL_2026.docx`) plus an anchor map (paragraphs, tables and charts to fill). Client content is
    replaced in place per §5.10, never re-laid out.
  - `energy_manager_report.xlsx`, `prelucrare_date.xlsx`: her layouts
- **Slots:** named anchors in the templates (e.g. `ch2.date_generale`, `ch4.electricitate.grafic`).
  A slot left unfilled in a draft stays visible only in the preview. **Final export requires every
  slot filled or its section `n/a`.**
- **Blocks:** Paragraph (style), BulletList, Table (house style; header row green/white; widths
  from content), Figure (image + caption), **NativeChart** (a real Word chart with its embedded
  worksheet: column/line/pie, her colours), PageBreak. Numbering of figures and tables, and the
  „În figura numărul X… / Conform tabelului numărul Y…" references, are resolved in one pass
  at render.
- **Output settings:**
  - TOC page numbers are computed from the engine's own PDF render and written into the TOC
    field result. There is no update-fields prompt on open (§5.10).
  - Romanian number formatting (`1.234,56`).
  - Fonts with full Romanian diacritics in charts.
- **Annual reuse:** a client's confirmed facts carry into next
  year's job. The engine re-fills the same template. It never diffs Word files.
- **Risk:** python-docx has no chart support. Native charts are built as raw chart parts
  (DrawingML + an embedded xlsx).
  - **Partly proven (2026-09-19, CLIENT-P1 PIEE):** the result opened cleanly in Word for Mac,
    with editable data. That covered rewriting her existing chart parts, embedding their
    workbooks, and adding native 3D pies.
  - **S0 still proves:** Word on Windows, and charts built from scratch for the audit.

### 5.8 `consumption_analysis`

This generates the section order shared by the PIEE and audit ch. 4:
producție → consum per purtător → consum echivalent (tep) → concluzii → eficiență / consum
specific per purtător → intensitate energetică → impact de mediu (+ audituri/investiții for the
PIEE).

- **Per section:** her table layouts, native charts (monthly per carrier, annual structure,
  trends), and sentences from **her real phrase patterns**, with numbers inserted and rule-based
  choices (creștere/scădere/constantă; the largest share; notable months).
- Deterministic; no LLM.
- The phrase bank is extracted from her audits and PIEEs (S7).
- **Two consumers, one analysis:**
  - Audit ch. 4 renders the blocks as new content.
  - The PIEE writes the same numbers and phrases into her existing tables, charts and sentences
    (§5.10).

### 5.9 Workflows in detail

#### W1 Facturi (`invoices`)

1. Upload a batch of PDFs.
2. Dedupe.
3. Parse: the ported parsers (EDS, MET, ENGIE, ALIVE, OMV Petrom, Next Energy, Getica, Electric
   Planners, Hidroelectrica, Enel/PPC); OCR for scans.
4. **Batch client identity:** Ema proposes the client (CUI/POD/name) once per batch, the user
   confirms, and the CUI/POD mapping is remembered.
5. Review the flagged invoices.
6. Export the workbook (the unchanged contract).

Gas and SEE documents are reported as "not supported yet".

#### W2 PIEE (`piee`)

1. Choose client + year.
2. Fill the slots:
   - Anexa 2–3 (year N)
   - Necesar info (year N)
   - optionally the auditor's *Prelucrare date*
3. Import into the dataset. The previous years come from last year's job or from her workbook.
4. Review the conflicts.
5. Generate from `piee_master.docx` (her latest finished PIEE), following the **PIEE format
   contract (§5.10)**:
   - **Date generale** ← clients + anexa (+ online for what the anexa lacks)
   - **Analiză** ← `consumption_analysis`, written into her existing tables and charts
   - **Audituri și investiții** ← anexa „Audit energetic" + „Solutii EE"
   - **Măsuri** ← „Solutii EE planificate"
   - **Bibliografie** ← anexa title + last audit (year, auditor)
6. Render to PDF, write the TOC page numbers, and run the contract's acceptance checks.
7. Output: `.docx` + generated *Prelucrare date* `.xlsx` (her layout, live formulas; a working
   file, not linked from the `.docx`).

#### W3 Audit (`audit`)

A long-lived job. Each stage is a function over the job folder, re-runnable
on its own:

| Stage | Does | Output |
|---|---|---|
| 1 Intake | upload in batches; sniff/convert; classify each file against the 13-item checklist + Necesar info + visit material; per-file status | `work/intake.json`, completeness („lipsesc: 6, 10") |
| 2 Extract | deterministic readers (Necesar info: energy, equipment, fleet, buildings, employees; Anexa 2–3; meter exports) + LLM extraction from permits, process-flow docs, schemes (structured output, source quote + page) | `facts.json` (state `extracted`), `dataset.json` |
| 3 Enrich | company (ANAF CUI service, registries), CAEN description, history (company site), location (public sources), map (OSM-based), equipment (brand + model → description, function, energy features, image) | facts (state `enriched`, URL + date) |
| 4 Confirm | the auditor confirms or edits facts and resolves conflicts; confirmed facts carry into next year | facts (state `confirmed`) |
| 5 Plan | compute each section's status from the template's section catalogue; user overrides (later / n/a) | `sections` |
| 6 Draft | per section: fixed text / data blocks / LLM narrative from facts only | `work/sections/<id>.json` |
| 7 Preview | the rendered `.docx` → PDF → a **paged, scrollable viewer** (all pages, like a PDF); per section: jump to its pages | `outputs/draft-<n>.docx` + `.pdf` |
| 8 Export | all sections `done` or `n/a` → final `.docx` | `outputs/final-<n>.docx` |

**Audit section catalogue** (the template tree with each section's kind and sources):

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
| 6.3 Măsuri specifice · 6.4 Sinteza | narrative + table + calc (NPV, payback) | auditor input + enrichment + calc |
| 7 Surse de finanțare | fixed text | template |

**Draft rules for AI narrative:**
- Only facts with a source may appear. A missing fact produces a `missing` status, never
  invented text.
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
  energetice CLIENT-P1 SA_2026.docx`, prepared for the auditor on 2026-09-19.
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
  - Then refresh **page numbers only**, computed from the engine's own PDF render.
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
- **Pies:** her pasted pie pictures become **native 3D pie charts** of the same size:
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
- No string from the previous client remains: name, address, product words, contact person,
  website.
- A page-by-page render is compared with her template: same styles and visuals, content changed.

### 5.11 Online enrichment (R5, R6)

- **What leaves the machine:** only public identifiers (CUI, company name, brand/model, locality)
  go to search/fetch. **Client documents never go to search.** They go only to the configured LLM
  provider (R15).
- **Sources, in order of trust:**
  1. official registries (ANAF CUI web service, ONRC data)
  2. the company's own website
  3. equipment manufacturers' pages / datasheets
  4. reputable encyclopaedic sources (locality/county data)
  5. general web (accepted only with a quoted snippet + URL, and flagged for review)
- **Every enriched fact stores:** URL, retrieval date, quoted snippet, confidence. It is shown
  with a "sursă" chip in the UI.
- **Images:** a manufacturer or open-licence source with attribution, otherwise a `later` item
  (a visit photo).
- Results are cached per client and per equipment model, so the same model is looked up only once.

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
- Prompts are versioned in code (`audit/prompts/…`), with style-guide excerpts from her real
  audits.
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
GET/PATCH  /jobs/{id}/facts              GET /jobs/{id}/conflicts  POST /jobs/{id}/conflicts/{c}
GET/PATCH  /jobs/{id}/sections           POST /jobs/{id}/sections/{s}/draft
GET        /jobs/{id}/preview.pdf        GET /jobs/{id}/outputs/{name}
GET/PUT    /settings                     (providers + keys → keyring, workspace path)

added for the design handoff (§5.18):
GET        /jobs/{id}/fields             ?status=pending|uncertain|accepted   (3c, 3f, 3g rows)
POST       /jobs/{id}/fields/{f}/accept  {value?}          POST /jobs/{id}/fields/accept-batch
GET        /jobs/{id}/log                POST /jobs/{id}/log/{entry}/undo     (Jurnal, R19)
GET        /sources/{source_id}/snippet.png   ?highlight=1  (page crop, R18)
GET        /sources/{source_id}/page.png      GET /sources/{source_id}/quote
GET        /jobs/{id}/export/checks      POST /jobs/{id}/export               (7a)
POST       /settings/providers/{p}/test  (the „verificată acum 2 h" state in 3i)
```

**CLI** (Typer; the same use cases; used by agents and golden tests):

```
ema serve
ema invoices extract <folder> --client <cui>
ema piee generate --client <cui> --year 2025 --anexa <file> --necesar <file> [--prelucrare <file>]
ema reporting generate --years 2023-2025
ema audit new --client <cui> --year 2026 ; ema audit add <job> <files…> ; ema audit run <job> <stage>
ema audit status <job>
```

**MCP** (slice S19):
- tools mirror the CLI
- confined to the workspace
- no delete, no final export (R14)

### 5.14 Errors, logging, observability

- **Typed errors:** `EmaError(code, user_message_ro, detail)`. The API returns problem+json.
  The UI shows the Romanian message; the detail and traceback go to `log.jsonl`.
- **Nothing is swallowed.** A worker's stderr is part of the log. A failed file or section
  shows its own error inline.
- The job log is the single place to debug. A "copy diagnostics" button in the UI zips the log +
  `job.json` (no client files).

### 5.15 Security and privacy

- **Local-first:** client data stays in the workspace. Data leaves the machine only via (a) LLM
  calls to the configured provider and (b) enrichment searches with public identifiers.
- Keys live in the OS keyring. Never in files, logs or the frontend.
- The API binds to `127.0.0.1` only, with a per-launch token between the window and the API.
- Client data never enters git (the reference library is outside the repo; tests read
  `$EMA_REFERENCE`).

### 5.16 Testing strategy

| Layer | What | Where it runs |
|---|---|---|
| Unit | calculations, label-finding, phrase rules, block rendering, parsers on small **synthetic** fixtures | CI + local |
| Golden (real data) | each slice's real case from the reference library: exact numbers, structure (heading tree, tables, captions, chart count), and invoice outputs matching delivered workbooks | local only (`$EMA_REFERENCE`), required before PRs |
| Document checks | generated docx vs the auditor's: heading tree, styles, fonts, table header colour, caption format, native charts present; for PIEEs the §5.10 acceptance list | golden |
| Contract | OpenAPI schema snapshot; import-linter | CI |
| AI | recorded LLM responses; a "no invented facts" check (every narrative sentence cites facts) | CI + golden |

### 5.17 Configuration

- One settings file in the workspace + the keyring.
- Settings: workspace path, the active AI provider (Gemini / OpenAI) + one model from the curated
  list (§5.12), OCR language, converter preference (auto / Word / LibreOffice), enrichment on/off.

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
- The HTML files are **design references, not code to port.** No inline styles are copied: the
  token table becomes the theme, and the components are rebuilt in our stack.
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
| 3j | **Structura raportului** | the section board: statuses, subsections, what holds a chapter, week view, client deadline (W3 stage 5) |
| 3d | **Raport Word** | generation watched chapter by chapter + the paged preview (W3 stages 6–7) |
| 3f | **Facturi** | the invoice table with per-cell sources and anomalies (W1) |
| 3g / 6c | **PIEE** | the measures table with sources and completeness (W2) |
| 3i | **Setări** | settings, no Save button; Gemini and OpenAI as independent keys, one marked IMPLICIT (§5.12) |
| 7a | **Export** (designed as „Predare") | pre-export checks + the package as a real file list + one primary action |
| 7b | Four shell states | empty · extracting · upload failed · nothing left to review |
| 7c | Three dialogs | delete module · re-run extraction · report already exists |
| 7d / 7e | Component sheet | the implementation reference, light and dark |

**Missing from the handoff, to be designed in the same language during S17b** (full list in
`OVERRIDES.md` §5):
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
| The report exports with `[de completat]` gaps | True for drafts. The **final** audit export needs every section done or n/a (§5.7); a PIEE marks missing data in red (R4c) | Draft export always allowed with the markers; final export keeps its gate |
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
Field       { id, chapter, key, label, value, unit?,
              state: extracted|supplied|enriched|calculated|manual,   // where it came from
              review: pending|accepted|corrected|rejected|missing,    // what the auditor did
              confidence: exact|partial|conflict|none,
              source?: SourceRef, alternatives?: {value, source}[],   // the two-document conflict
              reason?, history: {at, actor, from, to, action, batchId?}[] }
SourceRef   { id, docId, page?, bbox?, cell?, url?, retrievedAt?, quote? }
Measure     { id, name, detail?, investmentLei?, savingsMWh?, savingsTep?, paybackYears?,
              term?, responsible?, funding?, origin: anexa|audit|manual, source?,
              missing: (term|responsible|funding)[] }
SectionNode { id, number, title, status: ready|missing|later|na|drafted|done,
              later?: {reason: visit|measurements|thermography|map|chapter, date?, ref?},
              pages?, children[], note? }
JobDocument { id, name, kind, slot, pages?, sizeBytes, versions[],
              intake: read|reading|failed|needs_ocr|protected,
              failure?: {cause, threshold?, exits[]}, found?: string[] }
Report      { generatedAt?, editedExternallyAt?, version, path?, template }
Package     { files: {name, sizeBytes, kind}[], checks: {label, ok, detail}[] }
Settings    { theme, providers: {gemini, openai} each {present, maskedKey?, verifiedAt?},
              defaultProvider, extraction: {ocr, flagUncertain, autoAcceptExact} }
```

Three choices to challenge: the README's single field `status` is split into **state + review +
confidence**, because facts also arrive from enrichment and calculation, which the design never
had to show; `alternatives[]` carries the conflict rule; `missing[]` on a measure drives the
per-row „lipseşte" markers instead of a validation error.

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
~/Code/projects/
  ema/                  new repo (private GitHub: Energy-Management-Audit/ema)
  ema-reference/        reference library (moved from the campaign; never in git)
  _archive/ema-campaign/  old campaign (ARGUS, legacy repos, festivals), read-only; delete after Ema's first real job
```

Repo layout:

```
ema/
  AGENTS.md  CLAUDE.md→AGENTS.md  README.md  pyproject.toml  uv.lock
  .pre-commit-config.yaml  .importlinter  .github/workflows/ci.yml
  docs/PLAN.md (this file)  docs/ARCHITECTURE.md (1–2 pages, from §5, in S1)  docs/decisions/0001-packaging-and-resources.md
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
| `feature/<slice>` | one slice = one branch = one Conductor workspace | `dev` | `dev` (PR, squash) |
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
- **Conductor** setup lives in `.conductor/settings.toml` (committed): the setup script
  (`uv sync --all-groups && uv run pre-commit install`), branches deleted on archive, workspaces
  archived when their PR merges, and a branch-naming prompt (`feature/…`, `review/…`, `docs/…`,
  `hotfix/…`). Agent instructions are **not** repeated there: both agents load `AGENTS.md` on their
  own. `EMA_REFERENCE` reaches the agents through `.conductor/settings.local.toml`, gitignored
  because the path is this machine's. Workspaces start from `dev`.

### 6.3 Coding standards (tools, not prose)

| Standard | Enforced by |
|---|---|
| Formatting | `ruff format`; `prettier` |
| Lint + readability | `ruff check` (pycodestyle, pyflakes, isort, bugbear, pyupgrade, simplify, naming, pylint subset); complexity ≤ 10; limits on statements/branches/args per function |
| Types | `pyright` strict on `src/`; TS `strict` |
| Architecture | `import-linter` contracts (§5.1) |
| File size | a CI check: modules > ~400 lines fail |
| Tests | `pytest` unit (CI) + golden (local) |
| One gate | `pre-commit` locally = GitHub Actions CI |
| Design traceability | frontend commits and component names carry the design id (`feat(ui/3c): …`, `FieldReviewRow` "3c") (§5.18) |

**Principles (the one page in `AGENTS.md`):**
- SOLID applied pragmatically:
  - one responsibility per module/function
  - small interfaces only at real boundaries (readers, docx engine, LLM, storage, runner)
  - composition over inheritance
  - pure calculations
- No abstraction without a second real use.
- One code path per workflow.
- Errors surface with context.
- Domain names in business terms.
- Comments only for the non-obvious *why*.
- **Docs allowed:** README, AGENTS.md, PLAN.md, ARCHITECTURE.md, a few ADRs. No evidence files or
  AI artefacts.

### 6.4 Working model: Claude designs, Codex builds (in Conductor)

- **Claude** (product/design lead): this document, slice specs, acceptance, design review of
  diffs. **Codex** (lead engineer): implementation. **The user** arbitrates and merges.
- **Slice spec template** (level 3; lives in the Conductor workspace prompt + the PR
  description):
  1. **Goal**: 1–2 sentences + the requirement IDs (R…).
  2. **Context**: links to the § of this document.
  3. **Scope**: modules/files to create or change.
  4. **Interfaces**: function signatures, pydantic models, CLI/API shapes.
  5. **Behaviour rules**: edge cases taken from the real files.
  6. **Golden acceptance**: the exact command + expected result on the reference library.
  7. **Unit tests required.**
  8. **Out of scope.**
  9. **Done**: `uv run pre-commit run -a` · `uv run pytest` · the golden command.
- **Bounded review loop** (max 2 rounds each):
  1. Codex critiques the spec before building.
  2. Claude reviews the diff against the spec and the golden output.
  3. Codex adversarial review for engineering risk.
- **How the two agents work together in Conductor:** one workspace per slice, with a Claude chat
  and a Codex chat on the same branch. Claude writes or revises; Conductor's **Review** action,
  with Codex as the review model, reviews the branch diff; findings go back to Claude from the
  diff viewer as inline comments. Codex implements in its own chat; the Review action (Claude or
  Codex) checks it. Two rounds at most, then Vlad decides what remains, and the PR description
  records the outcome.

---

## 7. Roadmap (one slice = one `feature/…` branch = one Conductor workspace)

| # | Slice | Golden acceptance (real data) | Depends |
|---|---|---|---|
| S0 | **Spike:** native Word chart + house-style table/caption from Python | Chart opens and is editable in Word (Windows + Mac) and matches a AUDIT-01 chart visually | none |
| S1 | Repo skeleton: tooling, CI, import contracts, `core` workspace/jobs/logging/errors, CLI + API health | CI green; `ema --help`; job-folder round-trip | none |
| S2 | `core.office`: label-finding xls/xlsx readers; docx block engine (from S0) | A sample section rendered in her style, checked against her audit | S0, S1 |
| S2b | Legacy intake: type sniffing (incl. HTML-as-`.xls`) + `.doc` conversion with versions | All 12 CLIENT-A1 legacy files usable (5 `.xls` read, 7 `.doc` converted, text verified) | S1 |
| S3 | `energy_data` model, carriers + aliases, factors, `calc` | Reproduces CLIENT-P1 / CLIENT-P2 / CLIENT-A3 *Prelucrare* tep, specific consumption, emissions | S1 |
| S4 | Anexa 2–3 reader | All 38 real annexes parse; exact values on 5 (both form generations, 3 fuel-header variants) | S2, S3 |
| S5 | Necesar info reader (PIEE + audit versions) | CLIENT-P1, CLIENT-A3, CLIENT-A1 parse; monthly values match the sheets | S2, S3 |
| S5b | *Prelucrare date* reader (authoritative) + writer (her layout, formulas) | Reads CLIENT-P1 / CLIENT-A3 / CLIENT-P2; the generated CLIENT-P1 2023–2025 matches the reconstructed one | S3, S5 |
| S6 | Energy-manager report | Reproduces the delivered 2023 (37 companies) and 2025 CLIENT-R1/client-r2 reports | S4 |
| S7 | `consumption_analysis` + phrase bank | **CLIENT-A2** ch. 4 regenerated from the dataset taken from its own tables (then AUDIT-05 / AUDIT-02): same sections, tables, chart types, phrasing, numbers | S2, S3 |
| S8 | PIEE per the format contract (§5.10): clone her latest PIEE, change client content only | CLIENT-P1 2026 regenerated equals the golden (text, tables, chart caches, embedded workbooks, pies); piee-case-b: numbers match her final | S4, S5, S5b, S7 |
| S9 | Invoices port (**pypdfium2 + pdfplumber** instead of PyMuPDF) + batch identity + ALIVE OCR fix | 29/29 text invoices unchanged; CLIENT-I2 24 + ALIVE 13 exportable after one confirmation | S1 |
| S10 | Audit master template + section catalogue/status model + fixed chapters | Ch. 1 and ch. 7 identical to her text for a new client | S2 |
| S11 | Audit intake + checklist classification + completeness | CLIENT-A1 dossier fully read; checklist report correct | S2b, S10 |
| S12 | Structured extraction + ch. 2 identity + ch. 4 via S7 | CLIENT-A1 ch. 2 identity + ch. 4 from its Necesar info | S5, S7, S11 |
| S13 | Enrichment: company, location, map, equipment | CLIENT-A1: CAEN, address, location text, map, 10 equipment entries with sources | S12 |
| S14 | AI narrative drafting (ch. 2–3) + style guide | **CLIENT-A2** ch. 2–3 drafted from its dossier + enrichment and compared with her final; then CLIENT-A1 ch. 2–3 reviewed by the auditor: her structure, no invented facts | S13 |
| S15 | Ch. 5 from visit material (meter-display photos + thermal images → readings via vision → her measurement-sheet model) + ch. 6 measures and financials | **CLIENT-A2** ch. 5.1/5.2 readings match the values in her final; measures table + NPV/payback matching her method | S14 |
| S16a | API contract (OpenAPI) from the design handoff + mock server | Every screen in §5.18 maps to endpoints (including sources/snippet, fields, log/undo, export checks); frontend runs on mocks | S10 |
| S16 | Full HTTP API + SSE progress | OpenAPI covers every CLI use case | S8, S9, S12 |
| S17a | Design system: tokens (both themes) + the component layer from 7d/7e | The component sheet reproduced in light and dark; focus rings, row/button states, toggles match; paper stays paper in dark | S16a |
| S17b | Screens assembled from those components (3b–3j, 6a–6c, 7a–7c) + Clienți and Raportare | the auditor's journeys work end-to-end on the real API; each screen checked against its design id | S16, S17a |
| S18 | Windows packaging (pywebview + PyInstaller + Inno Setup) + settings + in-app update check | Installs, runs a PIEE job on Windows, detects a newer release | S17b |
| S19 | MCP server | An agent generates a PIEE and drafts an audit section headlessly | S16 |

**Parallel tracks:**
- S9 at any time after S1
- S3 alongside S0/S2
- S6 right after S4 (an early win for the auditor)
- design handoff in hand → S16a → S17a → S17b

---

## 8. Moving from the old world to the new

**Done on 2026-09-21:**
1. ✅ The library moved to `~/Code/projects/ema-reference/` (`$EMA_REFERENCE`); the scripts inside
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
5. Codex runs S0/S1 in Conductor.
6. Port the code per §5.19 in its slices (always from the archive, never by wholesale copy). The
   legacy repos are retired only once their parts are ported (S3, S7, S9), not before.
7. After Ema's first real delivered job:
   - archive the legacy GitHub repos (read-only)
   - delete `_archive/ema-campaign/` (this also deletes ARGUS, as accepted)
   - remove the old app from the auditor's PC (if installed)

Security to-dos (any time): rotate the Gemini key; change the shared mailbox password.

---

## 9. Open questions and what we need

**From Vlad**
1. ~~pywebview~~ and ~~repo layout/name~~: confirmed 09-19. The date of the §8 swap is still open.
2. Share the Claude Design output when ready (code export or screens).
3. Optional: install LibreOffice on the auditor's PC as a backup converter.
4. The topics in §10.

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
2. **Her blank base templates**, if they exist: the audit's metadata creator „Matrix" suggests a
   base Word template (.dotx/.docx) with her styles. That would replace reconstructing it (S10).
3. Confirm that her *Prelucrare date* values are always taken as-is from the client's Necesar
   info, and which one wins if they differ.
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
   - a weekly **"Backup" button + reminder** that writes a dated zip to a folder she chooses (e.g.
     OneDrive or an external disk); never a live-synced SQLite
   - recommend BitLocker disk encryption
4. **PDF licence:** pypdfium2 + pdfplumber replace PyMuPDF in S9 (PyMuPDF is AGPL-3.0).
5. **Document preview (decided 09-19):** a **paged, scrollable preview of the whole document**, like
   a PDF viewer (all pages, zoom, jump to a section's pages). **No editing engine** (out of scope).
   - Pipeline: the draft `.docx` → PDF via **Word** on Windows (`ExportAsFixedFormat`, exact
     fidelity) or **LibreOffice** headless (Mac/dev) → shown with **pdf.js** (Apache-2.0).
   - Plus a "Deschide în Word" button for the real `.docx`.
6. **Template and legislation upkeep.** *Default:*
   - templates are versioned per year
   - the auditor uploads a new template version in Settings, and Ema checks that its slots are intact
   - for the PIEE, her newest finished PIEE becomes the new base. Ema checks its anchor map
     (headings, tables, the 31 charts + pies) before using it.
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
    - TOC page numbers need a PDF render (Word on Windows, LibreOffice elsewhere), and
      LibreOffice pagination can differ from Word's
    - vision reading of meter photos (accuracy + confirmation UX)
    - LLM narrative quality vs the auditor's bar (S14 compared against the CLIENT-A2 final)
    - `.doc` conversion on machines without Office

**Docker: not for the product now.**
- the auditor needs a normal Windows app. Docker Desktop on Windows needs WSL2 and is heavy and
  unfamiliar.
- For development, `uv` already gives reproducible Python environments, and Conductor isolates
  work in worktrees.
- Docker becomes worth it for the future hosted backend (10.1) and possibly for CI jobs that need
  LibreOffice/Tesseract.
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

`~/Code/projects/ema-reference/` (`$EMA_REFERENCE`, moved out of the campaign on 2026-09-21):
**250 catalogued files, ~203 MB**
(2026-09-19; 206 files / 161 MB at the Step 1 build). Each file is listed in `catalog.csv` with its
sha256 and original location. Also: `README.md`, `_requirements/auditor-requirements.md`,
`_analysis/01–03`.

| Area | Contents |
|---|---|
| `audit/finished-audits/` | 6 human-written audits: AUDIT-02, AUDIT-01, AUDIT-04, AUDIT-03 (2026), CLIENT-A3 2022 (previous auditor), AUDIT-05 (`Cap 2-3-4 V2.docx`, ch. 1–4) |
| `audit/cases/` | CLIENT-A1 2026 (27 received files); audit-case-b (4 received + the original `.rar`; `visit/thermography/` 26 thermal images; `visit/electrical/tablou-electric-1..4/` 36 PAC3220 display photos + `electro.rar`; the auditor's final audit under `final/`); audit-case-c (Necesar info + Prelucrare) |
| `piee/` | 36 Anexa 2–3 (2025); CLIENT-I5 PIEE `MODEL_2026` (the auditor; the current PIEE base); CLIENT-P1 case (inputs; reconstructed workbook; `working/CLIENT-I5-format-generator/` scripts; `generated/`: the 18 Sep ARGUS version and **the 19 Sep CLIENT-I5-format golden**); CLIENT-P2 case (inputs, legacy output, final) |
| `invoices/` | 79 real invoices + 6 supporting docs by client (invoice-case-d, CLIENT-I5, CLIENT-I6, CLIENT-I2, CLIENT-I1); accepted workbooks; `by-supplier/` symlinks |
| `energy-manager-reporting/` | the auditor's model + delivered 2023, 2023–2025, 2025 CLIENT-R1/client-r2 reports |
| `design/handoff-2026-09-21/` | the design handoff: README spec, design system (7a–7e), light screens (3b–3j), dark screens (6a–6c), the superseded exploration and the current-UI recreation (§5.18) |

Roles: `received` · `working` · `generated` (never under `audit/`) · `final` · `visit`.
Cleanup: 1.4 GB moved to `~/.Trash/ema-cleanup-2026-09-18/`; the CLIENT-P1 working copies to
`~/.Trash/ema-cleanup-2026-09-19/` (both restorable until the Trash is emptied).
