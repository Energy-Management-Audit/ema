import { formatDate } from '../lib/format.ts'
import type { JobOverview } from '../api/types.ts'

export function formatCui(cui: string | number | null | undefined, vatPayer = false): string {
  if (cui == null) return '—'
  const raw = String(cui)
  const digits = raw.replace(/\D/g, '')
  if (!digits) return '—'
  return `${/^RO/i.test(raw) || vatPayer ? 'RO ' : ''}${digits}`
}

export function jobTag(job: Pick<JobOverview, 'type' | 'year'>): string {
  const prefix = job.type === 'audit' ? 'Audit' : job.type === 'piee' ? 'PIEE' : 'Facturi'
  return job.year == null ? prefix : `${prefix} ${String(job.year)}`
}

export function statusLine(job: Pick<JobOverview, 'type' | 'finalized' | 'approved_at'>): string {
  if (!job.finalized) return 'în lucru'
  if (job.type === 'invoices') return 'finalizat'
  return job.approved_at ? `exportat ${formatDate(job.approved_at)}` : 'finalizat'
}
