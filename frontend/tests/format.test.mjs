import assert from 'node:assert/strict'
import test from 'node:test'
import { formatBytes, formatNumber, parseNumber, rel } from '../src/lib/format.ts'

test('formatNumber: space thousands, decimal comma, D7 examples', () => {
  assert.equal(formatNumber('22164.05'), '22 164,05')
  assert.equal(formatNumber('248000'), '248 000')
  assert.equal(formatNumber('2.43', 'ani'), '2,4')
  assert.equal(formatNumber('2811.40'), '2 811,40')
  assert.equal(formatNumber('2.445'), '2,45')
  assert.equal(formatNumber('61.32', 'MWh'), '61,32')
  assert.equal(formatNumber('-1234.5'), '-1 234,50')
  assert.equal(formatNumber('12.00'), '12')
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
