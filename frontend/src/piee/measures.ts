// Measures of the Anexa 2–3 grouped as the PIEE shows them (3g, Q3 A).

import type { Field } from '../api/types.ts'
import { hasValue } from './dataset.ts'

export const GROUPS = [
  { group: 'planned', title: 'SOLUTII EE PLANIFICATE' },
  { group: 'existing', title: 'SOLUTII EE' },
  { group: 'audit', title: 'AUDIT ENERGETIC' },
] as const

export type MeasureView = {
  id: string
  group: string
  index: number
  columns: Partial<Record<string, Field>>
}

export const EDITABLE = [
  'investment_thousand_lei',
  'saving_mwh',
  'payback_years',
  'commissioning_year',
] as const

export function measureGroups(
  fields: Field[],
): { group: string; title: string; measures: MeasureView[] }[] {
  const byId = new Map<string, MeasureView>()
  for (const field of fields) {
    const parts = field.key.split('.')
    if (parts[0] !== 'measure' || parts.length !== 4 || !parts[1] || !parts[3]) continue
    const id = parts.slice(0, 3).join('.')
    const view = byId.get(id) ?? { id, group: parts[1], index: Number(parts[2]), columns: {} }
    view.columns[parts[3]] = field
    byId.set(id, view)
  }
  return GROUPS.map(({ group, title }) => ({
    group,
    title,
    measures: [...byId.values()]
      .filter((item) => item.group === group)
      .sort((a, b) => a.index - b.index),
  })).filter((item) => item.measures.length > 0)
}

/** The columns of a measure that were looked for and not found; each gets an editor. */
export function missingColumns(measure: MeasureView): string[] {
  return EDITABLE.filter((column) => {
    const field = measure.columns[column]
    return field !== undefined && !hasValue(field)
  })
}

export function firstWithoutTerm(fields: Field[]): MeasureView | null {
  for (const { measures } of measureGroups(fields)) {
    const found = measures.find((item) => !hasValue(item.columns.commissioning_year))
    if (found) return found
  }
  return null
}
