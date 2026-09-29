import assert from 'node:assert/strict'
import test from 'node:test'
import { FIELDS, JOB } from '../fixtures/piee/default.mjs'
import { CLIENT_OVERVIEW, CLIENT_ROUTES } from '../fixtures/clients/default.mjs'
import { withHarness } from './helpers.mjs'

test('F10 the measure row caps calculated payback and preserves raw source figures', async () => {
  const values = {
    'measure.planned.1.payback_years': '7.142857142857143',
    'measure.planned.1.investment_thousand_lei': '1234.561',
    'measure.planned.1.saving_mwh': '0.9948',
  }
  await withHarness(
    {
      path: `/app/piee/${JOB}/masuri`,
      routes: {
        [`GET /jobs/${JOB}/fields`]: {
          body: FIELDS.map((field) =>
            values[field.key] ? { ...field, value: values[field.key] } : field,
          ),
        },
      },
    },
    async ({ page }) => {
      const row = page.getByTestId('measure-row-measure.planned.1')
      await row.getByText('7,1 ani', { exact: false }).waitFor()
      await row.getByText('1 234,561', { exact: true }).waitFor()
      await row.getByText('0,9948', { exact: true }).waitFor()
      assert.equal(await row.getByText('7,142857142857143 ani', { exact: true }).count(), 0)
      await row.getByRole('button', { name: 'Anexa 2–3' }).click()
      await row.getByText('7,142857142857143 ani', { exact: true }).waitFor()
    },
  )
})

test('F10 the clients table caps computed total tep to two decimals', async () => {
  await withHarness(
    {
      path: '/app/clienti',
      routes: {
        ...CLIENT_ROUTES,
        'GET /clients/overview': {
          body: CLIENT_OVERVIEW.map((client, index) =>
            index === 0
              ? { ...client, consumption: { ...client.consumption, total_tep: '1234.5651' } }
              : client,
          ),
        },
      },
    },
    async ({ page }) => {
      const table = page.getByRole('table', { name: 'Clienţi' })
      await table.getByText('1 234,57 tep', { exact: true }).waitFor()
      assert.equal(await table.getByText('1 234,5651 tep', { exact: true }).count(), 0)
    },
  )
})
