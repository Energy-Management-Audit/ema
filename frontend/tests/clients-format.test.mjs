import assert from 'node:assert/strict'
import test from 'node:test'
import { formatCui, jobTag, statusLine } from '../src/clients/format.ts'

test('CUI and job labels keep Romanian display rules', () => {
  assert.equal(formatCui('RO12345678'), 'RO 12345678')
  assert.equal(formatCui('12345678'), '12345678')
  assert.equal(formatCui(12345678, true), 'RO 12345678')
  assert.equal(formatCui(null), '—')
  assert.equal(jobTag({ type: 'audit', year: 2025 }), 'Audit 2025')
  assert.equal(jobTag({ type: 'piee', year: 2025 }), 'PIEE 2025')
  assert.equal(jobTag({ type: 'invoices', year: null }), 'Facturi')
  assert.equal(statusLine({ type: 'invoices', finalized: true, approved_at: null }), 'finalizat')
})
