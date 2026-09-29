import type { ReportException, ReportingPreview } from '../api/reporting-types.ts'
import { plural as roCount } from '../lib/plural.ts'
import { formatNumber } from '../lib/format.ts'

export function severityLabel(code: string): 'EROARE' | 'ATENŢIE' | 'INFORMARE' {
  if (code === 'EROARE') return 'EROARE'
  if (code === 'INFORMARE') return 'INFORMARE'
  return 'ATENŢIE'
}

export function previewRows(preview: ReportingPreview, year: number, expanded: boolean) {
  const rows = preview.rows[String(year)] ?? []
  return expanded ? rows : rows.slice(0, 5)
}

export function exceptionSources(exceptions: ReportException[]): number {
  return new Set(exceptions.map((item) => item.source_name ?? item.client_id)).size
}

export function yearChip(year: number, count: number | undefined, first: boolean): string {
  if (count == null) return String(year)
  return `${String(year)} · ${first ? roCount(count, 'societate', 'societăţi') : String(count)}`
}

export function formatReportFigure(value: number): string {
  const formatted = formatNumber(value.toFixed(2))
  return formatted.includes(',') ? formatted : `${formatted},00`
}
