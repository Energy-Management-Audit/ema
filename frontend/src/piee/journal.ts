// A Jurnal entry (S5, 3c activity): the field, what the decision did, whether it can be undone.

import type { Decision } from '../api/types.ts'
import { formatNumber } from '../lib/format.ts'
import { fieldLabel } from './labels.ts'

export type JournalLine = {
  title: string
  detail: string
  outcome: 'accepted' | 'rejected' | 'info'
  undoable: boolean
}

function shown(value: unknown, unit: unknown, type: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  const text = typeof value === 'string' || typeof value === 'number' ? String(value) : '—'
  return type === 'number' ? formatNumber(text, typeof unit === 'string' ? unit : null) : text
}

export function journalLine(decision: Decision, year: number | null): JournalLine {
  const after = decision.after
  const before = decision.before
  const key =
    typeof after.key === 'string' ? after.key : typeof before.key === 'string' ? before.key : ''
  const label = typeof after.label === 'string' ? after.label : key
  const value = (field: typeof after) => shown(field.value, field.unit, field.value_type)
  let detail: string
  let outcome: JournalLine['outcome'] = 'accepted'
  switch (decision.action) {
    case 'choose':
      detail = `ales: ${value(after)}`
      break
    case 'correct':
      detail = `${value(before)} → ${value(after)}, scris de tine`
      break
    case 'reject':
      detail = 'respins'
      outcome = 'rejected'
      break
    case 'undo':
      detail = 'anulat'
      outcome = 'info'
      break
    default:
      detail = 'acceptat'
  }
  const undone = Boolean(decision.undone_by)
  return {
    title: fieldLabel(key, label, year),
    detail: undone ? `${detail} · anulat` : detail,
    outcome,
    undoable: !undone && decision.action !== 'undo',
  }
}

export function newestFirst(log: Decision[]): Decision[] {
  return [...log].reverse()
}
