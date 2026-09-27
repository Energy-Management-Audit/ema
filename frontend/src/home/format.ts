const WEEKDAYS = ['Duminică', 'Luni', 'Marţi', 'Miercuri', 'Joi', 'Vineri', 'Sâmbătă']
const MONTHS = [
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
]
const SHORT_MONTHS = [
  'ian',
  'feb',
  'mar',
  'apr',
  'mai',
  'iun',
  'iul',
  'aug',
  'sep',
  'oct',
  'noi',
  'dec',
]

export function formatDay(date: Date): string {
  return `${WEEKDAYS[date.getDay()]}, ${String(date.getDate())} ${MONTHS[date.getMonth()]}`
}

export function formatShortDate(iso: string, year = false): string {
  const date = new Date(iso)
  return `${String(date.getDate())} ${SHORT_MONTHS[date.getMonth()]}${year ? ` ${String(date.getFullYear())}` : ''}`
}

export function formatBackupTime(iso: string): string {
  const date = new Date(iso)
  return `${formatShortDate(iso, true)}, ${date.toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' })}`
}
