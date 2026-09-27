import type { InvoiceRow } from '../api/invoices-types.ts'

export type MonthBar = { month: string; height: number; missing: boolean; outlier: boolean }

export function monthBars(year: number, rows: InvoiceRow[]): MonthBar[] {
  const values = Array.from({ length: 12 }, (_, index) => {
    const month = `${String(year)}-${String(index + 1).padStart(2, '0')}`
    const matching = rows.filter((row) => row.month === month)
    return {
      month,
      value: matching.reduce((sum, row) => sum + Number(row.consumption_kwh ?? 0), 0),
      missing: matching.length === 0,
      outlier: matching.some((row) => row.outlier !== null),
    }
  })
  const max = Math.max(0, ...values.map((item) => item.value))
  return values.map((item) => ({
    month: item.month,
    height: item.missing ? 100 : max > 0 ? Math.max(4, Math.round((item.value / max) * 100)) : 4,
    missing: item.missing,
    outlier: item.outlier,
  }))
}
