import assert from 'node:assert/strict'
import test from 'node:test'
import { analysisYears, carrierTables } from '../src/piee/dataset.ts'
import { FIELDS } from './fixtures/piee/default.mjs'

test('one table per carrier in enum order, one row per year', () => {
  const tables = carrierTables(FIELDS)
  assert.deepEqual(
    tables.map((table) => table.carrier),
    ['electricity_grid', 'electricity_pv', 'natural_gas'],
  )
  const grid = tables[0]
  assert.equal(grid.unit, 'MWh')
  assert.deepEqual(
    grid.rows.map((row) => row.year),
    [2023, 2024, 2025],
  )
  assert.equal(grid.rows[0].months[0].field.value, '2811.40')
  assert.equal(grid.rows[0].annual.value, '30319.36')
})

test('annual-only years have no month cells; a missing month is marked', () => {
  const pv = carrierTables(FIELDS).find((table) => table.carrier === 'electricity_pv')
  assert.equal(pv.rows[0].months, null)
  const gap = FIELDS.filter((field) => field.key !== 'carrier.natural_gas.2024.05')
  const gas = carrierTables(gap).find((table) => table.carrier === 'natural_gas')
  assert.equal(gas.rows[1].months[4].kind, 'missing')
})

test('analysis years come from the carrier fields', () => {
  assert.deepEqual(analysisYears(FIELDS), [2023, 2024, 2025])
  assert.deepEqual(analysisYears([]), [])
})
