import assert from 'node:assert/strict'
import test from 'node:test'
import { FIELDS, JOB, routes } from '../fixtures/audit/default.mjs'
import { withHarness } from './helpers.mjs'

const J = `/jobs/${JOB.id}`

test('review filters and exact batch omit uncertain and photo readings', async () => {
  const meter = { ...FIELDS[0], id: 'meter-1', key: 'meter.panel.a', needs_confirmation: true }
  await withHarness(
    {
      path: `/app/audit/${JOB.id}/revizuire`,
      routes: {
        ...routes,
        [`GET ${J}/fields`]: { body: [...FIELDS, meter] },
        [`POST ${J}/fields/accept-batch`]: { body: [] },
      },
    },
    async ({ page, requests }) => {
      const accepted = page.waitForResponse((response) => response.url().endsWith('/accept-batch'))
      await page.getByRole('button', { name: 'Acceptă 1 câmp sigur' }).click()
      await accepted
      assert.deepEqual(requests.find((item) => item.path.endsWith('/accept-batch')).body, {
        fields: [[FIELDS[0].id, FIELDS[0].revision]],
      })
      await page.getByRole('button', { name: /Nesigure/ }).click()
      assert.equal(await page.getByText('Consum electric').count(), 1)
      assert.equal(await page.getByText('Numele societăţii').count(), 0)
      assert.equal(await page.getByText('meter.panel.a').count(), 0)
      await page
        .getByRole('button', { name: '1 valoare citită de pe fotografii aşteaptă confirmarea' })
        .click()
      await page.waitForURL(`**/app/audit/${JOB.id}/masuratori`)
    },
  )
})

test('pdf source opens a fetched crop and a correction reaches the decision endpoint', async () => {
  await withHarness(
    {
      path: `/app/audit/${JOB.id}/revizuire?camp=${FIELDS[0].id}`,
      routes: {
        ...routes,
        [`POST ${J}/fields/${FIELDS[0].id}/decide`]: { body: { id: 'decision-1' } },
      },
    },
    async ({ page, requests }) => {
      await page.getByRole('button', { name: 'Deschide pagina' }).waitFor()
      assert.ok(requests.some((item) => item.path.includes('/snippet.png?highlight=1')))
      assert.equal(await page.locator('img[src^="/evidence/"]').count(), 0)
      await page.getByRole('button', { name: 'Scrie altă valoare' }).click()
      await page.getByRole('textbox', { name: FIELDS[0].label }).fill('Atelier Nou')
      const decided = page.waitForResponse(
        (response) =>
          response.request().method() === 'POST' &&
          response.url().endsWith(`/fields/${FIELDS[0].id}/decide`),
      )
      await page.getByRole('button', { name: 'Salvează' }).click()
      await decided
      assert.deepEqual(
        requests.find((item) => item.path.endsWith(`/fields/${FIELDS[0].id}/decide`)).body,
        { action: 'correct', on_revision: FIELDS[0].revision, value: 'Atelier Nou' },
      )
    },
  )
})

test('online and calculated evidence present their origin without fetching a page image', async () => {
  const online = {
    ...FIELDS[0],
    id: 'online-1',
    key: 'audit.online',
    label: 'Factor online',
    state: 'enriched',
    evidence: ['online-1'],
  }
  const calc = {
    ...FIELDS[1],
    id: 'calc-1',
    key: 'audit.calc',
    label: 'Total calculat',
    state: 'calculated',
    evidence: ['calc-1'],
    confidence: 'exact',
    derivation: { formula_id: 'sum', inputs: [FIELDS[1].id], factor_version: '2026' },
  }
  await withHarness(
    {
      path: `/app/audit/${JOB.id}/revizuire`,
      routes: {
        ...routes,
        [`GET ${J}/fields`]: { body: [online, calc] },
        'GET /evidence/online-1/quote': {
          body: {
            id: 'online-1',
            provenance: 'online',
            file_sha: null,
            locator: { kind: 'url', url: 'https://www.example.org/' },
            retrieved_at: '2026-09-27T08:00:00Z',
            quote: 'Factor online',
            highlight: 'exact',
          },
        },
        'GET /evidence/calc-1/quote': {
          body: {
            id: 'calc-1',
            provenance: 'calculated',
            file_sha: null,
            locator: null,
            retrieved_at: '2026-09-27T08:00:00Z',
            quote: '',
            highlight: 'exact',
          },
        },
      },
    },
    async ({ page, requests }) => {
      const rows = page.locator('.ema-review-row')
      await rows.filter({ hasText: 'Factor online' }).locator('.ema-source-btn').click()
      await page.getByText('PAGINĂ WEB · instantaneu salvat').waitFor()
      await rows.filter({ hasText: 'Total calculat' }).locator('.ema-source-btn').click()
      await page.getByText('formula sum').waitFor()
      assert.equal(
        requests.some((item) => item.path.includes('/snippet.png')),
        false,
      )
    },
  )
})

test('rejected decisions stay in Acceptate and can be undone without a false all-accepted title', async () => {
  const rejected = { ...FIELDS[0], review: 'rejected' }
  const decision = {
    id: 'decision-reject',
    field_id: rejected.id,
    action: 'reject',
    target_kind: 'field',
    at: '2026-09-27T08:00:00Z',
    actor: 'user',
    on_revision: 1,
    before: FIELDS[0],
    after: rejected,
    batch_id: null,
    undone_by: null,
  }
  await withHarness(
    {
      path: `/app/audit/${JOB.id}/revizuire`,
      routes: {
        ...routes,
        [`GET ${J}/fields`]: { body: [rejected] },
        [`GET ${J}/log`]: { body: [decision] },
        [`POST ${J}/log/${decision.id}/undo`]: { body: { id: 'undo-1' } },
      },
    },
    async ({ page, requests }) => {
      await page.getByRole('heading', { name: 'Nu mai e nimic de confirmat.' }).waitFor()
      assert.equal(await page.getByText('Câmpul este acceptat').count(), 0)
      await page.getByRole('button', { name: 'Acceptate 1' }).click()
      await page
        .locator('.ema-review-row')
        .getByText(/^respins /)
        .waitFor()
      const undoing = page.waitForResponse((response) =>
        response.url().endsWith(`/log/${decision.id}/undo`),
      )
      await page.locator('.ema-review-row').getByRole('button', { name: 'Anulează' }).click()
      await undoing
      assert.ok(requests.some((item) => item.path.endsWith(`/log/${decision.id}/undo`)))
    },
  )
})

test('every accepted field shows the 7b completion state and structure exit', async () => {
  await withHarness(
    {
      path: `/app/audit/${JOB.id}/revizuire`,
      routes: {
        ...routes,
        [`GET ${J}/fields`]: { body: FIELDS.map((item) => ({ ...item, review: 'accepted' })) },
      },
    },
    async ({ page }) => {
      await page.getByRole('heading', { name: 'Toate cele 2 câmpuri sunt acceptate' }).waitFor()
      await page.getByRole('button', { name: 'Vezi 2 câmpuri acceptate' }).click()
      assert.equal(await page.locator('.ema-review-row').count(), 2)
      await page.getByRole('button', { name: 'Treci la structură' }).click()
      await page.waitForURL(`**/app/audit/${JOB.id}/structura`)
    },
  )
})

test('a conflict candidate and rejection send the chosen revision and decision', async () => {
  const conflict = {
    ...FIELDS[0],
    confidence: 'conflict',
    alternatives: [{ id: 'candidate-2', value: 'Atelier Alternativ', evidence: ['evidence-1'] }],
  }
  await withHarness(
    {
      path: `/app/audit/${JOB.id}/revizuire?camp=${conflict.id}`,
      routes: {
        ...routes,
        [`GET ${J}/fields`]: { body: [conflict] },
        [`POST ${J}/conflicts/${conflict.id}`]: { body: { id: 'decision-choose' } },
        [`POST ${J}/fields/${conflict.id}/decide`]: { body: { id: 'decision-reject' } },
      },
    },
    async ({ page, requests }) => {
      const chosen = page.waitForResponse((response) =>
        response.url().endsWith(`/conflicts/${conflict.id}`),
      )
      await page.getByRole('button', { name: 'Foloseşte Atelier Alternativ' }).click()
      await chosen
      assert.deepEqual(
        requests.find((item) => item.path.endsWith(`/conflicts/${conflict.id}`)).body,
        { candidate_id: 'candidate-2', on_revision: conflict.revision },
      )
      const rejected = page.waitForResponse((response) =>
        response.url().endsWith(`/fields/${conflict.id}/decide`),
      )
      await page.getByRole('button', { name: 'Respinge' }).click()
      await rejected
      assert.deepEqual(
        requests.find((item) => item.path.endsWith(`/fields/${conflict.id}/decide`)).body,
        { action: 'reject', on_revision: conflict.revision },
      )
    },
  )
})

test('batch undo in Jurnal reverses the decisions in latest-first order', async () => {
  const decisions = FIELDS.map((field, index) => ({
    id: `decision-${index}`,
    field_id: field.id,
    action: 'accept',
    target_kind: 'field',
    at: `2026-09-27T08:0${index}:00Z`,
    actor: 'user',
    on_revision: 1,
    before: field,
    after: { ...field, review: 'accepted' },
    batch_id: 'batch-1',
    undone_by: null,
  }))
  await withHarness(
    {
      path: `/app/audit/${JOB.id}/jurnal`,
      routes: {
        ...routes,
        [`GET ${J}/log`]: { body: decisions },
        [`POST ${J}/log/decision-1/undo`]: { body: { id: 'undo-1' } },
        [`POST ${J}/log/decision-0/undo`]: { body: { id: 'undo-0' } },
      },
    },
    async ({ page, requests }) => {
      const undoing = page.waitForResponse(
        (response) =>
          response.request().method() === 'POST' && response.url().endsWith('/log/decision-0/undo'),
      )
      await page.getByRole('button', { name: 'Anulează toate' }).click()
      await undoing
      assert.deepEqual(
        requests
          .filter((item) => item.method === 'POST' && item.path.includes('/undo'))
          .map((item) => item.path),
        [`${J}/log/decision-1/undo`, `${J}/log/decision-0/undo`],
      )
    },
  )
})

test('review activity names a batch, shows progress, and undoes newest first', async () => {
  const decisions = FIELDS.map((field, index) => ({
    id: `activity-${index}`,
    field_id: field.id,
    action: 'accept',
    target_kind: 'field',
    at: `2026-09-27T08:0${index}:00Z`,
    actor: 'user',
    on_revision: 1,
    before: field,
    after: { ...field, review: 'accepted' },
    batch_id: 'batch-activity',
    undone_by: null,
  }))
  await withHarness(
    {
      path: `/app/audit/${JOB.id}/revizuire`,
      routes: {
        ...routes,
        [`GET ${J}/log`]: { body: decisions },
        [`POST ${J}/log/activity-1/undo`]: { body: { id: 'undo-1' } },
        [`POST ${J}/log/activity-0/undo`]: { body: { id: 'undo-0' } },
      },
    },
    async ({ page, requests }) => {
      await page.getByText('acceptate toate deodată').waitFor()
      await page.getByText('CÂT A MAI RĂMAS').waitFor()
      const undoing = page.waitForResponse(
        (response) =>
          response.request().method() === 'POST' && response.url().endsWith('/log/activity-0/undo'),
      )
      await page.getByRole('button', { name: 'Anulează toate' }).click()
      await undoing
      assert.deepEqual(
        requests
          .filter((item) => item.method === 'POST' && item.path.includes('/undo'))
          .map((item) => item.path),
        [`${J}/log/activity-1/undo`, `${J}/log/activity-0/undo`],
      )
    },
  )
})
