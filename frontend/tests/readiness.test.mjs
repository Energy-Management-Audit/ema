import assert from 'node:assert/strict'
import test from 'node:test'
import {
  blockingFooter,
  blockingItems,
  currentFinal,
  exportChecks,
  previewPdf,
} from '../src/piee/readiness.ts'
import { CHECKS, FIELDS, FINAL_OUTPUTS, OUTPUTS, SUMMARY } from './fixtures/piee/default.mjs'

const missing = FIELDS.filter((field) => field.value === null)

test('blocking items: the conflict first, then the non-blocking gaps', () => {
  const items = blockingItems(CHECKS, FIELDS, missing, 2026)
  assert.deepEqual(items[0], {
    tone: 'err',
    status: 'conflict',
    label: 'Total 2025 vs Anexa „Date anuale”',
    detail: 'se decide o dată; decizia intră în Jurnal',
    fieldId: 'f-annual',
  })
  assert.ok(items.slice(1).every((item) => item.status === 'lipseşte'))
  assert.ok(items.some((item) => item.label === 'Nr. Registrul Comerţului'))
})

test('stale, import_required and other codes', () => {
  const checks = {
    readiness: {
      draft_ok: true,
      final_ok: false,
      blocking: [
        { code: 'stale', message: 'Datele PIEE s-au schimbat.' },
        { code: 'import_required', message: 'Documentele trebuie citite din nou.' },
        { code: 'package', message: 'Pachetul Word PIEE este invalid.' },
      ],
    },
    readiness_hash: 'h',
  }
  const items = blockingItems(checks, [], [], 2026)
  assert.deepEqual(
    items.map((item) => [item.tone, item.status, item.label]),
    [
      ['warn', 'ciornă veche', 'generează din nou programul'],
      ['warn', 'necitite', 'citeşte din nou documentele'],
      ['err', 'de rezolvat', 'Pachetul Word PIEE este invalid.'],
    ],
  )
  assert.equal(blockingFooter(checks), 'Exportul final se poate face după 3 decizii.')
  assert.equal(blockingFooter(CHECKS), 'Exportul final se poate face după 1 decizie.')
  assert.equal(
    blockingFooter({
      readiness: { draft_ok: true, final_ok: true, blocking: [] },
      readiness_hash: 'h',
    }),
    'Nimic nu blochează exportul final.',
  )
})

test('the four checks of 7a', () => {
  const checks = exportChecks(CHECKS, SUMMARY)
  assert.deepEqual(
    checks.map((item) => [item.tone, item.detail]),
    [
      ['warn', '5 / 7'],
      ['err', '22 164,05 tep'],
      ['ok', '0 deschise'],
      ['ok', 'la zi'],
    ],
  )
  assert.equal(checks[0].label, 'Toate cele 7 măsuri au termen, investiţie, economie şi recuperare')
})

test('preview only for a final docx with a PDF of the same run', () => {
  assert.equal(currentFinal(OUTPUTS), null)
  assert.equal(previewPdf(OUTPUTS), null)
  assert.equal(currentFinal(FINAL_OUTPUTS)?.id, 'out-final-1')
  assert.equal(previewPdf(FINAL_OUTPUTS)?.id, 'out-pdf-1')
  const noPdf = FINAL_OUTPUTS.filter((item) => item.id !== 'out-pdf-1')
  assert.equal(previewPdf(noPdf), null)
})

test('months_annual_mismatch blocks with the annual field and fails the annual check', () => {
  const annual = FIELDS.find((field) => /^carrier\.[a-z_]+\.\d{4}$/.test(field.key))
  const checks = {
    readiness: {
      draft_ok: true,
      final_ok: false,
      blocking: [
        {
          code: 'months_annual_mismatch',
          field_id: annual.id,
          message: 'Suma lunilor nu se potriveşte cu totalul anual.',
        },
      ],
    },
    readiness_hash: 'h',
  }
  const [item] = blockingItems(checks, FIELDS, [], 2026)
  assert.deepEqual(
    [item.tone, item.status, item.detail, item.fieldId],
    ['err', 'de corectat', 'suma lunilor diferă de totalul anual', annual.id],
  )
  assert.equal(exportChecks(checks, SUMMARY)[1].tone, 'err')
})
