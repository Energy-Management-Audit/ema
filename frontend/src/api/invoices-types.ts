export type InvoiceSource = { page: number; snippet: string }
export type InvoiceOutlier = { ratio: string; neighbours_mean_kwh: string }

export type InvoiceIdentity = {
  batch_id: string
  candidate: { client_id: string; cui: string | null; pod: string | null } | null
  confirmed: boolean
  evidence_ids: string[]
  revision: number
  name: string | null
  reasons: { printed: number; pods: string[]; other_client: number }
  pod_fill: { pod: string; files: string[]; source_count: number }[]
  memory: { kind: string; identifier: string; job: string; decision: string }[]
  files_total: number
  client_cui: string | null
}

export type InvoiceRow = {
  id: string
  month: string | null
  consumption_kwh: string | null
  source_evidence_ids: string[]
  anomalies: string[]
  file_name: string
  slot: string
  supplier: string | null
  invoice_number: string | null
  invoice_date: string | null
  status: string
  issues: string[]
  price_lei_kwh: string | null
  value_lei: string | null
  sources: Partial<Record<string, InvoiceSource>>
  outlier: InvoiceOutlier | null
}

export type InvoiceBatchView = {
  batch_id: string
  identity: InvoiceIdentity
  rows: InvoiceRow[]
  missing_months: string[]
  files: { slot: string; file_name: string; status: string; reason: string | null }[]
  totals: {
    months: number
    consumption_kwh: string
    value_lei: string
    price_avg_lei_kwh: string | null
  }
  year: number | null
  read_ended_at: string | null
}

export type InvoiceUpload = {
  added: { slot: string; file_name: string; sha: string }[]
  rejected: { file_name: string; code: string; reason: string }[]
}
