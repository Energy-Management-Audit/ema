import assert from 'node:assert/strict'
import test from 'node:test'
import { monthBars } from '../src/invoices/bars.ts'

test('twelve monthly bars leave a gap and flag the outlier', () => {
  const rows = [
    { month: '2026-01', consumption_kwh: '100', outlier: null },
    { month: '2026-03', consumption_kwh: '150', outlier: { ratio: '1.5' } },
    { month: '2026-04', consumption_kwh: '50', outlier: null },
  ]
  const bars = monthBars(2026, rows)
  assert.equal(bars.length, 12)
  assert.equal(bars[1].missing, true)
  assert.equal(bars[2].outlier, true)
  assert.equal(bars[2].height, 100)
  assert.ok(bars[0].height < bars[2].height)
})
