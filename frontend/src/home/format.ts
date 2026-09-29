import { formatDate } from '../lib/format.ts'

export function formatDay(date: Date): string {
  return formatDate(date, { year: false, long: true, weekday: true })
}

export function formatShortDate(iso: string, year = false): string {
  return formatDate(iso, { year })
}

export function formatBackupTime(iso: string): string {
  const date = new Date(iso)
  return `${formatDate(iso)}, ${date.toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' })}`
}
