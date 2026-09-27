export type ReportException = {
  client_id: string
  year: number | null
  code: string
  detail: string
  source_name: string | null
  beneficiary: string | null
  decision: string | null
  ref: string | null
}
export type ReportingRun = {
  id: string
  job_id: string
  created_at: string
  years: number[]
  client_ids: string[]
  state: 'running' | 'ready' | 'failed' | 'cancelled'
  exceptions: ReportException[]
  output_id: string | null
}
export type PreviewMeasure = {
  description: string
  saving_tep: number | null
  cost_thousand_lei: number | null
}
export type PreviewRow = {
  nr: number
  beneficiary: string
  client_id: string
  measures: PreviewMeasure[]
}
export type ReportingPreview = {
  years: number[]
  read: number
  companies_per_year: Record<string, number>
  rows: Record<string, PreviewRow[]>
}
