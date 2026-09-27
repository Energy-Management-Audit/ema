// The audit report contract (openapi/s17b-audit-report-diff.md): GET /jobs/{id}/audit/report.

export type RenderChapter = {
  number: number
  title: string
  section_id: string
  page: number | null
}

export type RenderMarker = {
  section_id: string
  label: string
}

export type RenderFailure = {
  section_id: string
  code: string
}

export type RenderUnitPlan = {
  client_name: string
  processes: number
  processes_source: 'schemes' | 'fisa' | 'default'
  carriers: string[]
  measured_panels: number
  thermal_measurements: boolean
  equipment_tables: number
  measures: number
}

export type RenderSummary = {
  kind: 'draft' | 'final'
  chapters: RenderChapter[]
  tables: number
  charts: number
  markers: RenderMarker[]
  fields_total: number
  fields_confirmed: number
  fields_manual: number
  unit_plan: RenderUnitPlan
  pdf: boolean
  toc_pages_set: boolean
  dropped: string[]
  failures: RenderFailure[]
}

export type ReportRun = {
  run_id: string
  state: 'running' | 'ready' | 'failed' | 'cancelled'
  ended_at: string | null
  current: boolean
  summary: RenderSummary | null
  docx_output_id: string | null
  pdf_output_id: string | null
}

export type AuditReport = {
  draft: ReportRun | null
  final: ReportRun | null
  word: boolean
}

/** The `stage_failed` payload of a run refused by a known problem; opaque failures have no
 * message. */
export type RunFailure = {
  code: string
  message: string | null
}

/** The part of a section's state the export checks read (GET /jobs/{id}/sections). */
export type AuditSection = {
  section_id: string
  status: string
  stale: boolean
}
