// Correcting found carrier figures on S3: the month editor (C2) and the months/annual banner (C1).

import assert from 'node:assert/strict'
import test from 'node:test'
import { CHECKS, FIELDS, JOB } from '../fixtures/piee/default.mjs'
import { count, settle, withHarness } from './helpers.mjs'

const J = `/jobs/${JOB}`
const MONTH = FIELDS.find((field) => field.id === 'f-natural_gas-2025-03')
const YEARLY = FIELDS.find((field) => field.id === 'f-natural_gas-2025')

const decided = (fieldId) => ({
  status: 200,
  body: {
    id: `d-${fieldId}`,
    at: '2026-09-26T09:00:00Z',
    actor: 'user',
    field_id: fieldId,
    on_revision: 1,
    action: 'correct',
    before: {},
    after: {},
  },
})

test('C2 a found month is click-to-correct with the decide API on its revision', async () => {
  await withHarness(
    { routes: { [`POST ${J}/fields/${MONTH.id}/decide`]: decided(MONTH.id) } },
    async ({ page, requests }) => {
      const table = page.getByTestId('carrier-table-natural_gas')
      await table.waitFor()
      await table.getByRole('button', { name: 'Corectează Gaz natural · Mar 2025' }).click()
      const editor = table.getByRole('textbox', { name: 'Gaz natural · Mar 2025' })
      await editor.fill('abc')
      await table.getByRole('button', { name: 'Salvează' }).click()
      await table.getByText('Valoarea nu este un număr.').waitFor()
      assert.equal(count(requests, 'POST', `${J}/fields/${MONTH.id}/decide`), 0)

      const fieldsBefore = count(requests, 'GET', `${J}/fields`)
      await editor.fill('5 100,5')
      await table.getByRole('button', { name: 'Salvează' }).click()
      await settle(page)
      const sent = requests.find((item) => item.path === `${J}/fields/${MONTH.id}/decide`)
      assert.deepEqual(sent.body, {
        action: 'correct',
        on_revision: MONTH.revision ?? 1,
        value: '5100.5',
      })
      assert.equal(await table.getByRole('textbox').count(), 0)
      assert.ok(count(requests, 'GET', `${J}/fields`) > fieldsBefore)
    },
  )
})

test('C2 Renunţă closes the month editor without a decision', async () => {
  await withHarness({}, async ({ page, requests }) => {
    const table = page.getByTestId('carrier-table-natural_gas')
    await table.getByRole('button', { name: 'Corectează Gaz natural · Mar 2025' }).click()
    await table.getByRole('button', { name: 'Renunţă' }).click()
    assert.equal(await table.getByRole('textbox').count(), 0)
    assert.equal(count(requests, 'POST', `${J}/fields/${MONTH.id}/decide`), 0)
  })
})

test('C1 the months/annual mismatch shows the M4 banner and corrects the annual value', async () => {
  const checks = {
    ...CHECKS,
    readiness: {
      ...CHECKS.readiness,
      blocking: [
        ...CHECKS.readiness.blocking,
        {
          code: 'months_annual_mismatch',
          field_id: YEARLY.id,
          message: 'Suma lunilor nu se potriveşte cu totalul anual.',
        },
      ],
    },
  }
  await withHarness(
    {
      routes: {
        [`GET ${J}/export/checks`]: { status: 200, body: checks },
        [`POST ${J}/fields/${YEARLY.id}/decide`]: decided(YEARLY.id),
      },
    },
    async ({ page, requests }) => {
      const banner = page.getByTestId('months-annual-banner')
      await banner.getByText('Suma lunilor nu se potriveşte cu totalul anual').waitFor()
      assert.match(await banner.innerText(), /Gaz natural 2025: totalul anual este 63 950 MWh/)
      await banner.getByRole('button', { name: 'Corectează totalul anual' }).click()
      await banner.getByRole('textbox', { name: 'Gaz natural 2025' }).fill('64 000')
      await banner.getByRole('button', { name: 'Salvează' }).click()
      await settle(page)
      const sent = requests.find((item) => item.path === `${J}/fields/${YEARLY.id}/decide`)
      assert.deepEqual(sent.body, {
        action: 'correct',
        on_revision: YEARLY.revision ?? 1,
        value: '64000',
      })
    },
  )
})
