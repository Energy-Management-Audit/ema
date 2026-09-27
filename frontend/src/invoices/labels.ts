export const MONTHS = [
  'ianuarie',
  'februarie',
  'martie',
  'aprilie',
  'mai',
  'iunie',
  'iulie',
  'august',
  'septembrie',
  'octombrie',
  'noiembrie',
  'decembrie',
] as const

export function monthName(month: string | null): string {
  if (!month) return 'fără lună'
  const number = Number(month.slice(5, 7))
  return MONTHS[number - 1] ?? 'fără lună'
}

export function statusWord(status: string): string {
  return (
    (
      {
        unsupported: 'nesuportate',
        incompatible: 'incompatibile',
        duplicate: 'duplicate',
        failed: 'eşuate',
        requires_review: 'de revizuit',
      } as Record<string, string>
    )[status] ?? status
  )
}

export function statusSingular(status: string): string {
  return (
    (
      {
        exportable: 'citită',
        unsupported: 'nesuportată',
        incompatible: 'incompatibilă',
        duplicate: 'duplicată',
        failed: 'eşuată',
        requires_review: 'de revizuit',
      } as Record<string, string>
    )[status] ?? status
  )
}

export function romanianForm(count: number, singular: string, plural: string): string {
  if (count === 1) return singular
  const lastHundred = count % 100
  return `${count !== 0 && (lastHundred === 0 || lastHundred >= 20) ? 'de ' : ''}${plural}`
}

export function romanianCount(count: number, singular: string, plural: string): string {
  return `${String(count)} ${romanianForm(count, singular, plural)}`
}

export function outlierPercent(ratio: string): number {
  return Math.round((Number(ratio) - 1) * 100)
}

export function formatInvoiceNumber(value: string | null, places = 0): string {
  if (value === null) return '—'
  const number = Number(value)
  if (!Number.isFinite(number)) return '—'
  return number
    .toLocaleString('ro-RO', {
      useGrouping: true,
      minimumFractionDigits: places,
      maximumFractionDigits: places,
    })
    .replace(/[.\u00a0\u202f]/g, ' ')
}
