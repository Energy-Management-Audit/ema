// Romanian figures for the UI (docs/PLAN.md §5.18): space thousands, decimal comma, unit after
// a space. Values arrive as JSON strings so no binary rounding happens before display.

const THIN = ' '

function groupThousands(integer: string): string {
  return integer.replace(/\B(?=(\d{3})+(?!\d))/g, THIN)
}

/** Half-up rounding on the decimal string itself, so `2.445` stays `2,45`. */
function roundDecimal(value: string, places: number): string {
  const negative = value.startsWith('-')
  const digits = negative ? value.slice(1) : value
  const [integer = '0', fraction = ''] = digits.split('.')
  if (fraction.length <= places) return `${negative ? '-' : ''}${integer}.${fraction}`
  const scaled = BigInt(integer + fraction.slice(0, places))
  const rounded = Number(fraction[places]) >= 5 ? scaled + 1n : scaled
  const text = rounded.toString().padStart(places + 1, '0')
  const head = text.slice(0, text.length - places)
  const tail = text.slice(text.length - places)
  return `${negative ? '-' : ''}${head}.${tail}`
}

export function formatNumber(
  value: string | number,
  unit?: string | null,
  calculated = false,
): string {
  const text = typeof value === 'number' ? String(value) : value.trim()
  if (!/^-?\d+(\.\d+)?$/.test(text)) return text
  const places = unit === 'ani' ? 1 : 2
  const [integer = '0', fraction = ''] = text.split('.')
  if (fraction === '' || (calculated && /^0*$/.test(fraction))) return groupThousands(integer)
  const rounded = calculated ? roundDecimal(text, places) : text
  const [head = '0', tail = ''] = rounded.split('.')
  const negative = head.startsWith('-')
  const grouped = groupThousands(negative ? head.slice(1) : head)
  return `${negative ? '-' : ''}${grouped},${calculated ? tail.padEnd(places, '0') : tail}`
}

export function withUnit(value: string, unit?: string | null): string {
  return unit ? `${formatNumber(value, unit)} ${unit}` : formatNumber(value, unit)
}

export const AMBIGUOUS_NUMBER = 'Scrie 12500 sau 12,5'

export const NOT_A_NUMBER = 'Valoarea nu este un număr.'

/** Accepts `22 164,05`, `22164,05` or `22164.05`; returns the dot-decimal string the API takes. */
export function parseNumber(input: string): { value: string } | { error: string } {
  const compact = input.trim().replace(/[\s  ]/g, '')
  if (!compact.includes(',') && /\.\d{3}$/.test(compact)) return { error: AMBIGUOUS_NUMBER }
  const normal = compact.includes(',') ? compact.replace(/\./g, '').replace(',', '.') : compact
  if (!/^-?\d+(\.\d+)?$/.test(normal)) return { error: NOT_A_NUMBER }
  return { value: normal }
}

export function formatBytes(bytes: number): string {
  const mib = 1024 * 1024
  if (bytes < mib) return `${String(Math.max(1, Math.round(bytes / 1024)))} KB`
  if (bytes < 10 * mib) return `${(bytes / mib).toFixed(1).replace('.', ',')} MB`
  return `${String(Math.round(bytes / mib))} MB`
}

const MONTHS = ['ian', 'feb', 'mar', 'apr', 'mai', 'iun', 'iul', 'aug', 'sep', 'oct', 'noi', 'dec']

/** Relative time for the activity column and the draft status. */
export function rel(iso: string, now: Date = new Date()): string {
  const then = new Date(iso)
  const seconds = Math.max(0, Math.floor((now.getTime() - then.getTime()) / 1000))
  if (seconds < 60) return `acum ${String(seconds)} s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `acum ${String(minutes)} min`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `acum ${String(hours)} h`
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const startOfThen = new Date(then.getFullYear(), then.getMonth(), then.getDate()).getTime()
  const days = Math.round((startOfToday - startOfThen) / 86_400_000)
  if (days <= 1) return 'ieri'
  if (days < 7) return `acum ${String(days)} zile`
  return formatDate(then, { year: then.getFullYear() !== now.getFullYear(), padDay: true })
}

const LONG_MONTHS = [
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
const WEEKDAYS = ['Duminică', 'Luni', 'Marţi', 'Miercuri', 'Joi', 'Vineri', 'Sâmbătă']

/** Handoff month forms, shared by calendar dates, source dates and activity ranges. */
export function formatDate(
  iso: string | Date,
  { year = true, long = false, weekday = false, utc = false, padDay = false } = {},
): string {
  const date = typeof iso === 'string' ? new Date(iso) : iso
  const day = String(utc ? date.getUTCDate() : date.getDate())
  const month = utc ? date.getUTCMonth() : date.getMonth()
  const dayOfWeek = utc ? date.getUTCDay() : date.getDay()
  const dateYear = utc ? date.getUTCFullYear() : date.getFullYear()
  return `${weekday ? `${WEEKDAYS[dayOfWeek]}, ` : ''}${padDay ? day.padStart(2, '0') : day} ${(long ? LONG_MONTHS : MONTHS)[month]}${year ? ` ${String(dateYear)}` : ''}`
}

export function elapsed(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds))
  return `${String(Math.floor(safe / 60)).padStart(2, '0')}:${String(safe % 60).padStart(2, '0')}`
}
