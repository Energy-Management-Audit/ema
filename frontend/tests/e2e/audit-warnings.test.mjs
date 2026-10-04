import assert from 'node:assert/strict'
import test from 'node:test'
import { FIELDS, JOB, routes } from '../fixtures/audit/default.mjs'
import { withHarness } from './helpers.mjs'

const J = `/jobs/${JOB.id}`
const WARNINGS = [
  {
    code: 'data_count_conflict',
    field_id: FIELDS[1].id,
    message: 'Număr diferit în două documente: Consum electric.',
    evidence_ids: ['evidence-2', 'evidence-1'],
  },
  {
    code: 'data_month_repeat',
    field_id: FIELDS[0].id,
    message: 'Luni consecutive egale: electricitate, 3 şi 4.',
    evidence_ids: ['evidence-1', 'evidence-2'],
  },
]

test('7f lists the readiness data warnings and opens each source in the evidence viewer', async () => {
  const checks = routes[`GET ${J}/export/checks`].body
  await withHarness(
    {
      path: `/app/audit/${JOB.id}/revizuire`,
      routes: {
        ...routes,
        [`GET ${J}/export/checks`]: {
          body: { ...checks, readiness: { ...checks.readiness, warnings: WARNINGS } },
        },
      },
    },
    async ({ page, requests }) => {
      const section = page.getByRole('region', { name: 'Date de verificat' })
      await section.getByText('DATE DE VERIFICAT · NU BLOCHEAZĂ RAPORTUL').waitFor()
      const row = section.locator('.ema-review-row').filter({ hasText: WARNINGS[0].message })
      await row.getByText('de verificat', { exact: true }).waitFor()
      await row.getByText(FIELDS[1].label, { exact: true }).waitFor()
      await section
        .locator('.ema-review-row')
        .filter({ hasText: WARNINGS[1].message })
        .getByText(FIELDS[0].label, { exact: true })
        .waitFor()
      const pdf = row.getByRole('button', { name: 'source.pdf · pag. 1' })
      await row.getByRole('button', { name: 'source.xlsx · Date!B2' }).waitFor()
      assert.equal(await pdf.getAttribute('aria-expanded'), 'false')
      await pdf.click()
      assert.equal(await pdf.getAttribute('aria-expanded'), 'true')
      await row.getByRole('button', { name: 'Deschide pagina' }).waitFor()
      await row.getByText('DE CE E MARCAT', { exact: true }).waitFor()
      assert.ok(
        requests.some((item) => item.path === '/evidence/evidence-1/snippet.png?highlight=1'),
      )
      await row.getByRole('button', { name: 'source.xlsx · Date!B2' }).click()
      await row.getByText('Date!B2', { exact: true }).waitFor()
      assert.equal(await pdf.getAttribute('aria-expanded'), 'false')
      await page.getByRole('button', { name: /^Acceptate/ }).click()
      assert.equal(await page.getByRole('region', { name: 'Date de verificat' }).count(), 0)
    },
  )
})

test('7f stays out of the queue when the readiness has no warnings', async () => {
  await withHarness({ path: `/app/audit/${JOB.id}/revizuire`, routes }, async ({ page }) => {
    await page.getByRole('button', { name: /^În aşteptare/ }).waitFor()
    await page.getByText(FIELDS[1].label).first().waitFor()
    assert.equal(await page.getByRole('region', { name: 'Date de verificat' }).count(), 0)
  })
})
