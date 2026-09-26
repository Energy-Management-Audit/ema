// The three-year consumption tables of M4, built from `carrier.*` fields. No arithmetic: totals
// are the fields' own values.

import type { Field } from '../api/types.ts'
import { CARRIER_ORDER } from './labels.ts'

export type MonthCell = { kind: 'value'; field: Field } | { kind: 'missing'; field: Field | null }

export type CarrierRow = {
  year: number
  annual: Field | null
  /** null when the year has no monthly figures at all (annual only). */
  months: MonthCell[] | null
}

export type CarrierTable = { carrier: string; unit: string; rows: CarrierRow[] }

type Parsed = { carrier: string; year: number; month: number | null }

function parse(key: string): Parsed | null {
  const parts = key.split('.')
  if (parts[0] !== 'carrier' || parts.length < 3 || parts.length > 4) return null
  if (!parts[1] || !/^\d{4}$/.test(parts[2] ?? '')) return null
  const month = parts.length === 4 ? Number(parts[3]) : null
  if (month !== null && !(month >= 1 && month <= 12)) return null
  return { carrier: parts[1], year: Number(parts[2]), month }
}

export function hasValue(field: Field | null | undefined): field is Field {
  return field?.value !== null && field?.value !== undefined
}

export function carrierTables(fields: Field[]): CarrierTable[] {
  type Slot = { annual: Field | null; months: Map<number, Field> }
  const byCarrier = new Map<string, Map<number, Slot>>()
  for (const field of fields) {
    const parsed = parse(field.key)
    if (!parsed) continue
    const years = byCarrier.get(parsed.carrier) ?? new Map<number, Slot>()
    byCarrier.set(parsed.carrier, years)
    const slot = years.get(parsed.year) ?? { annual: null, months: new Map<number, Field>() }
    years.set(parsed.year, slot)
    if (parsed.month === null) slot.annual = field
    else slot.months.set(parsed.month, field)
  }
  const carriers = [...byCarrier.keys()].sort((a, b) => order(a) - order(b) || a.localeCompare(b))
  return carriers.map((carrier) => {
    const years = byCarrier.get(carrier) ?? new Map<number, Slot>()
    const rows: CarrierRow[] = [...years.entries()]
      .sort(([a], [b]) => a - b)
      .map(([year, slot]) => ({
        year,
        annual: slot.annual,
        months:
          slot.months.size === 0
            ? null
            : Array.from({ length: 12 }, (_, index): MonthCell => {
                const field = slot.months.get(index + 1) ?? null
                return hasValue(field) ? { kind: 'value', field } : { kind: 'missing', field }
              }),
      }))
    return { carrier, unit: headingUnit(rows), rows }
  })
}

function order(carrier: string): number {
  const index = CARRIER_ORDER.indexOf(carrier)
  return index < 0 ? CARRIER_ORDER.length : index
}

function headingUnit(rows: CarrierRow[]): string {
  const counts = new Map<string, number>()
  for (const row of rows) {
    const units = [row.annual?.unit, ...(row.months ?? []).map((cell) => cell.field?.unit)]
    for (const unit of units) if (unit) counts.set(unit, (counts.get(unit) ?? 0) + 1)
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? ''
}

/** The analysis years shown in the tab label and the page title. */
export function analysisYears(fields: Field[]): number[] {
  const years = new Set<number>()
  for (const field of fields) {
    const parsed = parse(field.key)
    if (parsed) years.add(parsed.year)
  }
  return [...years].sort((a, b) => a - b)
}
