import assert from 'node:assert/strict'
import test from 'node:test'
import { sourceLabel } from '../src/audit/sources.ts'
import { statusLine } from '../src/clients/format.ts'
import { formatShortDate } from '../src/home/format.ts'
import { formatBytes, formatDate, formatNumber, parseNumber, rel } from '../src/lib/format.ts'

test('formatNumber: space thousands, decimal comma, D7 examples', () => {
  assert.equal(formatNumber('22164.05'), '22 164,05')
  assert.equal(formatNumber('248000'), '248 000')
  assert.equal(formatNumber('2.43', 'ani', true), '2,4')
  assert.equal(formatNumber('2811.40'), '2 811,40')
  assert.equal(formatNumber('2.445', null, true), '2,45')
  assert.equal(formatNumber('61.32', 'MWh'), '61,32')
  assert.equal(formatNumber('-1234.5'), '-1 234,5')
  assert.equal(formatNumber('12.00'), '12,00')
})

test('parseNumber accepts Romanian and dot input and sends the dot-decimal string', () => {
  assert.deepEqual(parseNumber('22 164,05'), { value: '22164.05' })
  assert.deepEqual(parseNumber('22164,05'), { value: '22164.05' })
  assert.deepEqual(parseNumber('22164.05'), { value: '22164.05' })
  assert.deepEqual(parseNumber('22 163,5'), { value: '22163.5' })
  assert.deepEqual(parseNumber('abc'), { error: 'Valoarea nu este un număr.' })
  assert.deepEqual(parseNumber(''), { error: 'Valoarea nu este un număr.' })
})

test('formatBytes: KB under a MiB, one decimal under 10 MiB, whole MB above', () => {
  assert.equal(formatBytes(90 * 1024), '90 KB')
  assert.equal(formatBytes(4_299_161), '4,1 MB')
  assert.equal(formatBytes(14 * 1024 * 1024), '14 MB')
})

test('rel: seconds, minutes, hours, yesterday, days, then the date', () => {
  const now = new Date('2026-09-25T12:00:00')
  assert.equal(rel('2026-09-25T11:59:30', now), 'acum 30 s')
  assert.equal(rel('2026-09-25T11:48:00', now), 'acum 12 min')
  assert.equal(rel('2026-09-25T09:00:00', now), 'acum 3 h')
  assert.equal(rel('2026-09-24T08:00:00', now), 'ieri')
  assert.equal(rel('2026-09-21T08:00:00', now), 'acum 4 zile')
  assert.equal(rel('2026-03-14T08:00:00', now), '14 mar')
  assert.equal(rel('2025-03-14T08:00:00', now), '14 mar 2025')
})

test('F9 ambiguous thousands never becomes a decimal silently', () => {
  for (const value of ['12.500', '-12.500', '1.234', '1.234.567', '12.500 ']) {
    assert.deepEqual(parseNumber(value), { error: 'Scrie 12500 sau 12,5' })
  }
  for (const [input, value] of [
    ['12500', '12500'],
    ['12,5', '12.5'],
    ['12.5', '12.5'],
    ['0.9948', '0.9948'],
    ['1.234,56', '1234.56'],
  ]) {
    assert.deepEqual(parseNumber(input), { value })
  }
})

test('F10 review values retain the digits that distinguish sources', () => {
  for (const [value, shown] of [
    ['0.9948', '0,9948'],
    ['0.9912', '0,9912'],
    ['11.368', '11,368'],
    ['0.0042', '0,0042'],
    ['1234.561', '1 234,561'],
    ['1234.564', '1 234,564'],
  ]) {
    assert.equal(formatNumber(value), shown)
  }
  assert.equal(formatNumber('1234.564', null, true), '1 234,56')
  assert.equal(formatNumber('1234.564'), '1 234,564')
})

test('F19 dates use the handoff month forms consistently', () => {
  const months = [
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
  for (const [index, month] of months.entries()) {
    assert.equal(formatDate(new Date(2026, index, 15)), `15 ${month} 2026`)
  }
  assert.equal(formatDate('2026-09-29T00:00:00Z', { utc: true }), '29 sep 2026')
  assert.equal(formatDate('2026-09-29', { year: false, long: true }), '29 septembrie')
})

test('F19 source, client and home dates share the same September form', () => {
  const at = '2026-09-29T08:00:00Z'
  assert.equal(formatShortDate(at, true), '29 sep 2026')
  assert.equal(
    statusLine({ type: 'audit', finalized: true, approved_at: at }),
    'exportat 29 sep 2026',
  )
  assert.equal(
    sourceLabel({ retrieved_at: at, locator: { kind: 'url', url: 'https://example.org' } }),
    'example.org · 29 sep 2026',
  )
})
