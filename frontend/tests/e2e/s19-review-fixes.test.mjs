import assert from 'node:assert/strict'
import test from 'node:test'
import { FIELDS, JOB, routes } from '../fixtures/audit/default.mjs'
import { JOB as PIEE_JOB, SUMMARY } from '../fixtures/piee/default.mjs'
import { withHarness } from './helpers.mjs'

const J = `/jobs/${JOB.id}`

test('F18 counted review copy omits nonexistent exact fields and preserves the handoff sentence', async () => {
  const uncertain = Array.from({ length: 7 }, (_, index) => ({
    ...FIELDS[1],
    id: `uncertain-${index}`,
    confidence: 'partial',
    review: 'pending',
  }))
  for (const exactCount of [0, 4]) {
    await withHarness(
      {
        path: `/app/audit/${JOB.id}/revizuire`,
        routes: {
          ...routes,
          [`GET ${J}/fields`]: {
            body: [
              ...uncertain,
              ...Array.from({ length: exactCount }, (_, index) => ({
                ...FIELDS[0],
                id: `exact-${index}`,
              })),
            ],
          },
        },
      },
      async ({ page }) => {
        await page.getByText('Începe cu 7 câmpuri nesigure', { exact: true }).waitFor()
        await page
          .getByText(`Raportul se poate genera după ultimele ${7 + exactCount}.`, { exact: true })
          .waitFor()
        if (exactCount)
          await page
            .getByText(
              'Restul 4 au potrivire exactă în document — le poţi accepta pe toate deodată.',
              { exact: true },
            )
            .waitFor()
        else assert.equal(await page.getByText(/^Restul/).count(), 0)
      },
    )
  }
})

test('F10 conflict alternatives retain differing decimals; F19 journal and calculation inputs use Romanian numbers', async () => {
  const numeric = {
    ...FIELDS[1],
    value: '1234.561',
    value_type: 'number',
    confidence: 'conflict',
    alternatives: [{ id: 'other', value: '1234.564', evidence: ['evidence-1'] }],
  }
  const input = {
    ...FIELDS[0],
    id: 'input-1',
    label: 'Intrare',
    value_type: 'number',
    value: '22164.05',
  }
  const calculated = {
    ...FIELDS[1],
    id: 'calc-1',
    label: 'Total calculat',
    state: 'calculated',
    review: 'accepted',
    value_type: 'number',
    value: '1234.564',
    evidence: ['calc-source'],
    derivation: { formula_id: 'sum', inputs: ['input-1'] },
  }
  const decision = {
    id: 'correct-1',
    field_id: input.id,
    action: 'correct',
    at: '2026-09-29T08:00:00Z',
    before: { value: '22164.05' },
    after: { value: '22170.5' },
    undone_by: null,
  }
  await withHarness(
    {
      path: `/app/audit/${JOB.id}/revizuire?camp=${numeric.id}`,
      routes: {
        ...routes,
        [`GET ${J}/fields`]: { body: [numeric, input, calculated] },
        [`GET ${J}/log`]: { body: [decision] },
        'GET /evidence/calc-source/quote': {
          body: {
            id: 'calc-source',
            provenance: 'calculated',
            highlight: 'exact',
            retrieved_at: '2026-09-29T08:00:00Z',
          },
        },
      },
    },
    async ({ page }) => {
      await page.getByRole('button', { name: 'Foloseşte 1 234,564', exact: true }).waitFor()
      await page.getByText('1 234,561 MWh', { exact: true }).waitFor()
      await page.getByText('22 164,05 → 22 170,5, scris de tine', { exact: true }).waitFor()
      await page.getByRole('button', { name: /Acceptate/ }).click()
      const row = page.locator('.ema-review-row').filter({ hasText: 'Total calculat' })
      await row.getByText('1 234,56 MWh', { exact: true }).waitFor()
      await row.locator('.ema-source-btn').click()
      await page.getByText('1 234,564 MWh', { exact: true }).waitFor()
      await page.getByText('Intrare · 22 164,05', { exact: true }).waitFor()
    },
  )
})

test('F18 a partial measure summary names a single missing measure correctly', async () => {
  await withHarness(
    {
      path: `/app/piee/${PIEE_JOB}/masuri`,
      routes: {
        [`GET /jobs/${PIEE_JOB}/piee/summary`]: {
          body: { ...SUMMARY, savings_mwh: { ...SUMMARY.savings_mwh, missing: ['missing-1'] } },
        },
      },
    },
    async ({ page }) => {
      await page.getByText('fără 1 măsură', { exact: true }).waitFor()
      assert.equal(await page.getByText('fără 1 măsuri', { exact: true }).count(), 0)
    },
  )
})
