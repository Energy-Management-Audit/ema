import { formatDate } from '../lib/format.ts'
import type { Decision } from '../api/types.ts'
import { sectionStateLabel } from './outline.ts'

export function decisionLabel(decision: Decision): string {
  if (decision.target_kind === 'section')
    return `Secţiune: ${sectionStateLabel(typeof decision.after.status === 'string' ? decision.after.status : '', typeof decision.after.reason === 'string' ? decision.after.reason : null, decision.after.stale === true)}`
  if (decision.action === 'accept') return 'acceptat'
  if (decision.action === 'correct') return 'scris de tine'
  if (decision.action === 'reject') return 'respins'
  if (decision.action === 'choose') return 'aleasă o valoare'
  return 'anulat'
}

export function isoWeek(date: string): string {
  const day = new Date(date)
  day.setUTCHours(0, 0, 0, 0)
  day.setUTCDate(day.getUTCDate() + 4 - (day.getUTCDay() || 7))
  const year = day.getUTCFullYear()
  const first = new Date(Date.UTC(year, 0, 1))
  return `${String(year)}-${String(Math.ceil(((day.getTime() - first.getTime()) / 86400000 + 1) / 7)).padStart(2, '0')}`
}

export function byWeek(decisions: Decision[]): [string, Decision[]][] {
  const weeks = new Map<string, Decision[]>()
  for (const decision of decisions) {
    const week = isoWeek(decision.at)
    weeks.set(week, [...(weeks.get(week) ?? []), decision])
  }
  return [...weeks].sort(([a], [b]) => b.localeCompare(a))
}

export function weekRange(week: string): string {
  const [year, number] = week.split('-').map(Number)
  const fourth = new Date(Date.UTC(year, 0, 4))
  const monday = new Date(fourth)
  monday.setUTCDate(fourth.getUTCDate() - (fourth.getUTCDay() || 7) + 1 + (number - 1) * 7)
  const sunday = new Date(monday)
  sunday.setUTCDate(monday.getUTCDate() + 6)
  return `${formatDate(monday, { year: false, utc: true })}–${formatDate(sunday, { year: false, utc: true })}`
}
