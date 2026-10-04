// Mirrors the OpenAPI schemas this app uses (openapi/ema.v1.json); tests/contract-types.test.mjs
// checks every property name against the contract. One property per line.

export type Job = {
  id: string
  type: 'invoices' | 'piee' | 'audit' | 'reporting'
  client_slug: string
  year: number | null
  state: string
  revision: number
}

export type JobOverview = {
  id: string
  type: 'invoices' | 'piee' | 'audit' | 'reporting'
  client_slug: string
  year: number | null
  state: string
  revision: number
  client_name: string | null
  created_at: string
  updated_at: string
  final_ok: boolean | null
  blocking: number | null
  next: string | null
  readiness_error: string | null
  approved_at: string | null
  finalized: boolean
}

export type NewJobResult = { id: string }
export type DeleteResult = { deleted: boolean }

export type Client = {
  id: string
  name?: string | null
  cui?: string | null
  caen?: string | null
  sites: unknown[]
  contacts: unknown[]
  revision: number
  anaf_refreshed_at?: string | null
}

export type Candidate = {
  id: string
  value: unknown
  evidence: string[]
}

export type Derivation = {
  formula_id: string
  inputs: string[]
  factor_version: string
}

export type Field = {
  id: string
  job_id: string
  chapter?: string
  key: string
  label: string
  value_type: 'number' | 'text' | 'year' | 'date' | 'enum'
  unit?: string | null
  decimals?: number
  grouping?: boolean
  required?: boolean
  value?: unknown
  revision?: number
  state: 'supplied' | 'extracted' | 'enriched' | 'calculated' | 'manual'
  presence: 'found' | 'not_found' | 'failed'
  review?: 'pending' | 'accepted' | 'corrected' | 'rejected'
  confidence?: 'exact' | 'partial' | 'conflict' | 'none'
  evidence?: string[]
  derivation?: Derivation | null
  alternatives?: Candidate[]
  chosen?: string | null
  failure?: string | null
  needs_confirmation?: boolean
}

export type VisitPhoto = { sha: string; slot: string; name: string }
export type VisitPanel = { id: string; label: string; photos: VisitPhoto[] }
export type VisitView = { panels: VisitPanel[]; thermal: VisitPhoto[] }

export type Decision = {
  id: string
  at: string
  actor: 'ema' | 'user' | 'agent'
  field_id: string
  target_kind?: 'field' | 'section'
  on_revision: number
  action: 'accept' | 'correct' | 'reject' | 'choose' | 'status' | 'undo'
  detail?: string | null
  before: Partial<Field> & Record<string, unknown>
  after: Partial<Field> & Record<string, unknown>
  batch_id?: string | null
  undone_by?: string | null
}

export type Cell = {
  kind?: 'cell'
  sheet: string
  ref: string
}

export type Evidence = {
  id: string
  provenance: 'document' | 'online' | 'calculated' | 'manual'
  file_sha?: string | null
  file_name?: string | null
  locator?: { kind: string; sheet?: string; ref?: string } | null
  method: string
  retrieved_at: string
  quote?: string | null
  trust_reason?: string | null
  highlight: 'exact' | 'page' | 'none'
  derivation?: Derivation | null
  decision_id?: string | null
}

export type Issue = {
  code: string
  field_id?: string | null
  message: string
  evidence_ids?: string[]
}

export type Readiness = {
  draft_ok: boolean
  final_ok: boolean
  blocking?: Issue[]
  warnings?: Issue[]
  next?: string[]
}

export type ExportChecks = {
  readiness: Readiness
  readiness_hash: string
  final: { output_id: string; created_at: string; files: string[] } | null
}

export type ExportResponse = {
  approved_at: string
  files: { name: string; path: string }[]
  folder: string
}

export type Output = {
  id: string
  version: number
  kind: 'draft' | 'final'
  media_type: string
  size_bytes: number
  name: string
  created_at: string | null
  run_id: string
  stage: string
}

export type Approval = {
  id: string
  job_id: string
  output_id: string
  readiness_hash: string
  on_decision: string | null
  at: string
  exported_at: string | null
  actor: 'ema' | 'user' | 'agent'
}

export type SlotVersion = {
  job_id: string
  slot: string
  version: number
  file_sha: string
  origin: string
  converted_from: string | null
  original_name: string | null
  slot_revision: number
}

export type FileVersion = {
  version: number
  sha: string
  name: string
  size_bytes: number
}

export type ClientFile = {
  sha: string
  name: string
  size_bytes: number
  kind: string
  intake: 'stored'
}

export type PrelucrareState = {
  input?: { file_id?: string; years?: number[] } | null
  output?: { id?: string; version?: number } | null
  authority: 'input_for_covered_years' | 'generated' | 'none'
}

export type SummaryFigure = {
  value: string | null
  unit: string
  field_ids: string[]
  missing: string[]
}

export type PieeSummary = {
  total_tep: SummaryFigure
  annual_check: 'match' | 'decided' | 'mismatch' | 'missing'
  savings_mwh: SummaryFigure
  investment_thousand_lei: SummaryFigure
  measures_total: number
  measures_complete: number
  measures_without_term: number
}

export type RunStart = {
  run_id: string
  stage: string
  state: 'running'
}

export type RunRecord = {
  id: string
  stage: string
  state: 'running' | 'ready' | 'failed' | 'cancelled'
  publication?: string | null
  error?: string | null
  started_at: string
  ended_at: string | null
}

export type JobStatus = {
  id: string
  type: string
  state: string
  revision: number
  runs: RunRecord[]
}

export type SettingsView = {
  theme: 'light' | 'dark'
  default_provider?: 'gemini' | 'openai' | null
  providers: Record<string, unknown>
  extraction: Record<string, unknown>
}

export type SessionResult = {
  csrf: string
}

export type CancelResult = {
  cancelled: boolean
}

export type ConflictChoice = {
  candidate_id: string
  on_revision: number
}

export type DecisionInput = {
  action: 'accept' | 'correct' | 'reject' | 'choose'
  on_revision: number
  value?: unknown
  alternative?: string | null
  reason?: string | null
}

export type PieeImport = {
  on_revision: number
}

export type PieeGenerate = {
  kind: 'draft'
  on_revision: number
}

export type StageInput = {
  on_revision: number
}

export type ExportInput = {
  output_id: string
  readiness_hash: string
  confirm: true
  dest_dir: string | null
}

export type SlotInput = {
  file_sha: string
}

export type PrelucrareInput = {
  file_id: string
  role: 'input'
}

/** A server-sent progress event (`GET /jobs/{id}/events`). */
export type JobEvent = {
  seq: number
  job_id: string
  run_id: string
  stage: string
  type: string
  at: string
  payload: Record<string, unknown>
}
