import assert from 'node:assert/strict'
import test from 'node:test'
import { FIELDS, JOB, routes } from '../fixtures/audit/default.mjs'
import {
  FINAL_CHECKS,
  FINAL_OUTPUTS,
  FINAL_RUN,
  ANSWERED,
  REPORT,
  J as REPORT_J,
  JOB as REPORT_JOB,
  reportRoutes,
} from '../fixtures/audit-report/default.mjs'
import { problem } from './harness.mjs'
import { withHarness } from './helpers.mjs'

const J = `/jobs/${JOB.id}`
const field = (id, label, value, evidence, extra = {}) => ({
  ...FIELDS[1],
  id,
  key: `synthetic.${id}`,
  label,
  value,
  confidence: 'exact',
  evidence: [evidence],
  ...extra,
})
// Each source is a cell of its own, so its button names the cell and its panel needs no crop.
const cell = (id, ref, quote) => ({
  status: 200,
  body: {
    id,
    provenance: 'document',
    file_sha: 'sha',
    file_name: 'date.xlsx',
    locator: { kind: 'cell', sheet: 'Date', ref },
    method: 'questionnaire',
    retrieved_at: '2026-09-27T08:00:00Z',
    quote,
    highlight: 'exact',
  },
})
const WARNING_FIELDS = [
  field('gpl-qty', 'Cantitate GPL 2025', '0', 'ev-gpl-qty'),
  field('gpl-cost', 'Cost GPL 2025', '18400', 'ev-gpl-cost'),
  field('count', 'Număr autovehicule', '2', 'ev-count-a', {
    confidence: 'conflict',
    alternatives: [{ id: 'alt-3', value: 3, evidence: ['ev-count-b'] }],
  }),
  field('m1', 'Motorină 2025 · ianuarie', '1200', 'ev-m1'),
  field('m2', 'Motorină 2025 · februarie', '1200', 'ev-m2'),
  field('m3', 'Motorină 2025 · martie', '0', 'ev-m3'),
  field('d2024', 'Motorină 2024', '0', 'ev-d2024'),
  field('d2025', 'Motorină 2025', '5100', 'ev-d2025'),
]
// One warning per readiness code, with the field each of its two sources must open with.
const CASES = [
  [
    'data_gpl_cost_no_quantity',
    'GPL: cost pozitiv şi cantitate zero în 2025.',
    [
      ['ev-gpl-qty', 'A1', 'Cantitate GPL 2025'],
      ['ev-gpl-cost', 'A2', 'Cost GPL 2025'],
    ],
  ],
  [
    'data_count_conflict',
    'Număr diferit în două documente: Număr autovehicule.',
    [
      ['ev-count-a', 'A3', 'Număr autovehicule'],
      ['ev-count-b', 'A4', 'Număr autovehicule'],
    ],
  ],
  [
    'data_month_repeat',
    'Luni consecutive egale: motorină 2025, ianuarie şi februarie.',
    [
      ['ev-m1', 'A5', 'Motorină 2025 · ianuarie'],
      ['ev-m2', 'A6', 'Motorină 2025 · februarie'],
    ],
  ],
  [
    'data_quarter_in_month',
    'Consum concentrat într-o lună: motorină 2025, luna ianuarie.',
    [
      ['ev-m1', 'A5', 'Motorină 2025 · ianuarie'],
      ['ev-m3', 'A7', 'Motorină 2025 · martie'],
    ],
  ],
  [
    'data_change_refused',
    'Schimbare omisă: motorină, 2024–2025: bază zero.',
    [
      ['ev-d2024', 'A8', 'Motorină 2024'],
      ['ev-d2025', 'A9', 'Motorină 2025'],
    ],
  ],
]
const WARNINGS = CASES.map(([code, message, sources]) => ({
  code,
  field_id: WARNING_FIELDS.find((item) => item.label === sources[0][2]).id,
  message,
  evidence_ids: sources.map(([id]) => id),
}))
const EVIDENCE = Object.fromEntries(
  CASES.flatMap(([, , sources]) => sources).map(([id, ref, label]) => [
    `GET /evidence/${id}/quote`,
    cell(id, ref, `${label}: valoare din document`),
  ]),
)
const checks = routes[`GET ${J}/export/checks`].body
const warningRoutes = {
  ...routes,
  ...EVIDENCE,
  [`GET ${J}/fields`]: { body: WARNING_FIELDS },
  [`GET ${J}/export/checks`]: {
    body: { ...checks, readiness: { ...checks.readiness, warnings: WARNINGS } },
  },
}
const section = (page) => page.getByRole('region', { name: 'Date de verificat' })

test('7f lists all five warning codes and opens each source with the field it backs', async () => {
  await withHarness(
    { path: `/app/audit/${JOB.id}/revizuire`, routes: warningRoutes },
    async ({ page }) => {
      await section(page).getByText('DATE DE VERIFICAT · NU BLOCHEAZĂ RAPORTUL').waitFor()
      assert.equal(await section(page).locator('.ema-review-row').count(), CASES.length)
      for (const [, message, sources] of CASES) {
        const row = section(page).locator('.ema-review-row').filter({ hasText: message })
        await row.getByText('de verificat', { exact: true }).waitFor()
        await row.getByText(sources[0][2], { exact: true }).first().waitFor()
        for (const [, ref, label] of sources) {
          const source = row.getByRole('button', { name: `date.xlsx · Date!${ref}` })
          await source.click()
          assert.equal(await source.getAttribute('aria-expanded'), 'true')
          await row.getByText('DE CE E MARCAT', { exact: true }).waitFor()
          await row.getByText(`${label}: valoare din document`).waitFor()
          await row.getByRole('button', { name: 'Scrie altă valoare' }).click()
          await row.getByRole('textbox', { name: label, exact: true }).waitFor()
        }
      }
      const conflict = section(page).locator('.ema-review-row').filter({ hasText: CASES[1][1] })
      await conflict.getByRole('button', { name: 'date.xlsx · Date!A4' }).click()
      await conflict.getByRole('button', { name: 'Foloseşte 3' }).waitFor()
      await page.getByRole('button', { name: /^Acceptate/ }).click()
      assert.equal(await section(page).count(), 0)
    },
  )
})

test('7f: a source that fails to load names the problem and retries', async () => {
  let attempts = 0
  await withHarness(
    {
      path: `/app/audit/${JOB.id}/revizuire`,
      routes: {
        ...warningRoutes,
        'GET /evidence/ev-d2025/quote': () => {
          attempts += 1
          return attempts === 1
            ? problem('evidence_missing', 404, 'Sursa nu mai există în dosar.')
            : EVIDENCE['GET /evidence/ev-d2025/quote']
        },
      },
    },
    async ({ page }) => {
      const row = section(page).locator('.ema-review-row').filter({ hasText: CASES[4][1] })
      await row.getByRole('button', { name: 'date.xlsx · Date!A8' }).waitFor()
      await row.getByRole('button', { name: 'Sursa' }).click()
      const failure = row.getByRole('alert')
      await failure.getByText('Nu am putut încărca sursa').waitFor()
      await failure.getByText('Sursa nu mai există în dosar.').waitFor()
      assert.equal(await row.getByText('Se încarcă…').count(), 0)
      await failure.getByRole('button', { name: 'Încearcă din nou' }).click()
      await row.getByText('Motorină 2025: valoare din document').waitFor()
      await row.getByRole('button', { name: 'date.xlsx · Date!A9' }).waitFor()
      assert.equal(attempts, 2)
    },
  )
})

test('7f stays out of the queue when the readiness has no warnings', async () => {
  await withHarness({ path: `/app/audit/${JOB.id}/revizuire`, routes }, async ({ page }) => {
    await page.getByRole('button', { name: /^În aşteptare/ }).waitFor()
    await page.getByText(FIELDS[1].label).first().waitFor()
    assert.equal(await section(page).count(), 0)
  })
})

test('a readiness with warnings only stays exportable', async () => {
  await withHarness(
    {
      path: `/app/audit/${REPORT_JOB}/predare`,
      routes: {
        ...reportRoutes,
        [`GET ${REPORT_J}/outputs`]: { status: 200, body: FINAL_OUTPUTS },
        [`GET ${REPORT_J}/sections`]: { status: 200, body: ANSWERED },
        [`GET ${REPORT_J}/audit/report`]: { status: 200, body: { ...REPORT, final: FINAL_RUN } },
        [`GET ${REPORT_J}/export/checks`]: {
          status: 200,
          body: { ...FINAL_CHECKS, readiness: { ...FINAL_CHECKS.readiness, warnings: WARNINGS } },
        },
      },
    },
    async ({ page }) => {
      const rows = page.locator('[data-testid^="export-check-"]')
      await rows.first().waitFor()
      assert.deepEqual(
        await rows.evaluateAll((nodes) => nodes.map((node) => node.dataset.tone)),
        Array.from({ length: await rows.count() }, () => 'ok'),
      )
      const approve = page.getByRole('button', { name: 'Aprobă şi exportă' })
      await approve.waitFor()
      assert.equal(await approve.isEnabled(), true)
    },
  )
})
