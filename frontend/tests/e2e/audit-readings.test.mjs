import assert from 'node:assert/strict'
import test from 'node:test'
import { problem } from './harness.mjs'
import { withHarness } from './helpers.mjs'

const id = 'audit-synthetic'
const J = `/jobs/${id}`
const sha = 'a'.repeat(64)
const reading = {
  id: 'reading-1',
  job_id: id,
  chapter: 'ch5.electric_fisa',
  key: `meter.panel-1.${sha.slice(0, 8)}.voltage_ln.l1`,
  label: 'voltage_ln l1',
  value_type: 'number',
  unit: 'V',
  value: '230.00',
  revision: 3,
  state: 'extracted',
  presence: 'found',
  review: 'pending',
  confidence: 'exact',
  evidence: ['ev-1'],
  alternatives: [],
  needs_confirmation: true,
}
const job = { id, type: 'audit', client_slug: 'synthetic', year: 2026, state: 'open', revision: 7 }
const visit = {
  panels: [
    {
      id: 'panel-1',
      label: 'Panel 1',
      photos: [{ sha, slot: 'visit/meter/Panel 1/display.png', name: 'display.png' }],
    },
  ],
  thermal: [],
}

test('3c reading row confirms one value, shows its photo and undoes the decision', async () => {
  let current = { ...reading }
  let decisions = []
  await withHarness(
    {
      path: `/app/audit/${id}/masuratori`,
      routes: {
        'GET /jobs': { status: 200, body: [job] },
        'GET /clients': { status: 200, body: [] },
        [`GET ${J}`]: { status: 200, body: job },
        [`GET ${J}/fields`]: () => ({ status: 200, body: [current] }),
        [`GET ${J}/visit`]: { status: 200, body: visit },
        [`GET ${J}/log`]: () => ({ status: 200, body: decisions }),
        [`GET ${J}/export/checks`]: {
          status: 200,
          body: {
            readiness: { draft_ok: true, final_ok: false, blocking: [], warnings: [], next: [] },
            readiness_hash: 'hash',
          },
        },
        'GET /evidence/ev-1/snippet.png?highlight=1': {
          status: 200,
          contentType: 'image/png',
          body: 'png',
        },
        [`POST ${J}/fields/reading-1/decide`]: (request) => {
          assert.deepEqual(JSON.parse(request.postData()), { action: 'accept', on_revision: 3 })
          current = { ...current, revision: 4, review: 'accepted', needs_confirmation: false }
          decisions = [
            {
              id: 'decision-1',
              field_id: 'reading-1',
              action: 'accept',
              on_revision: 3,
              before: reading,
              after: current,
              actor: 'user',
              at: '2026-09-27T00:00:00Z',
              undone_by: null,
            },
          ]
          return { status: 200, body: decisions[0] }
        },
        [`POST ${J}/log/decision-1/undo`]: () => {
          current = { ...reading, revision: 5 }
          decisions = []
          return { status: 200, body: { id: 'undo-1' } }
        },
        [`POST ${J}/stages/readings`]: problem(
          'ai_client_disabled',
          403,
          'Citirea fotografiilor aşteaptă aprobarea.',
        ),
      },
    },
    async ({ page, requests }) => {
      await page.getByText('Panel 1').waitFor()
      await page.getByText('230 V').waitFor()
      assert.equal(await page.getByText('Acceptă tot').count(), 0)
      await page.getByRole('button', { name: 'display.png' }).click()
      await page.locator('img[src="/evidence/ev-1/snippet.png?highlight=1"]').waitFor()
      await page.getByRole('button', { name: 'Acceptă' }).first().click()
      await page.getByText('acceptat').waitFor()
      await page.getByRole('button', { name: 'Anulează' }).click()
      await page.getByText('de verificat').waitFor()
      await page.getByRole('button', { name: 'Citeşte fotografiile' }).click()
      await page.getByText('Citirea fotografiilor aşteaptă aprobarea.').first().waitFor()
      assert.ok(
        requests.some((item) => item.path === `${J}/stages/readings` && item.method === 'POST'),
      )
    },
  )
})
