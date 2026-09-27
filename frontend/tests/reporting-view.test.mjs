import assert from 'node:assert/strict'
import test from 'node:test'
import {
  exceptionSources,
  formatReportFigure,
  previewRows,
  severityLabel,
  yearChip,
} from '../src/reporting/view.ts'

test('severity labels and source count map to the screen', () => {
  assert.equal(severityLabel('EROARE'), 'EROARE')
  assert.equal(severityLabel('REVIZUIRE'), 'ATENŢIE')
  assert.equal(severityLabel('INFORMARE'), 'INFORMARE')
  assert.equal(
    exceptionSources([
      { source_name: 'a.xlsx', client_id: 'one' },
      { source_name: 'a.xlsx', client_id: 'one' },
      { source_name: 'b.xlsx', client_id: 'two' },
    ]),
    2,
  )
  assert.equal(yearChip(2025, 36, true), '2025 · 36 de societăţi')
  assert.equal(yearChip(2025, 1, true), '2025 · 1 societate')
  assert.equal(yearChip(2024, 31, false), '2024 · 31')
  assert.equal(formatReportFigure(12), '12,00')
  assert.equal(formatReportFigure(1234.5), '1 234,50')
})

test('preview shows the first five beneficiaries, then all', () => {
  const rows = Array.from({ length: 7 }, (_, index) => ({
    nr: index + 1,
    beneficiary: `Exemplu ${index}`,
  }))
  const preview = { rows: { 2025: rows } }
  assert.equal(previewRows(preview, 2025, false).length, 5)
  assert.equal(previewRows(preview, 2025, true).length, 7)
})
