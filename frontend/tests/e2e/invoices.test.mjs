import assert from 'node:assert/strict'
import test from 'node:test'
import {
  J,
  JOB,
  acceptedBatch,
  acceptedIdentity,
  batch,
  checks,
  confirmedChecks,
  decision,
  identity,
  invoiceRoutes,
  job,
  output,
  ready,
  status,
} from '../fixtures/invoices/default.mjs'
import { withHarness } from './helpers.mjs'

test('empty upload starts reading and can be stopped', async () => {
  let uploaded = false
  const routes = {
    ...invoiceRoutes,
    [`GET ${J}/slots`]: () => ({ status: 200, body: uploaded ? ['invoices/0001'] : [] }),
    [`GET ${J}/status`]: () => ({
      status: 200,
      body: uploaded
        ? { ...status, runs: [{ id: 'run-new', stage: 'invoices', state: 'running' }] }
        : { ...status, state: 'created', runs: [] },
    }),
    [`POST ${J}/invoices/files`]: () => {
      uploaded = true
      return {
        status: 200,
        body: {
          added: [{ slot: 'invoices/0001', file_name: 'one.pdf', sha: 'sha-one' }],
          rejected: [],
        },
      }
    },
    [`POST ${J}/stages/invoices`]: {
      status: 202,
      body: { run_id: 'run-new', stage: 'invoices', state: 'running' },
    },
    [`GET ${J}/events`]: {
      status: 200,
      contentType: 'text/event-stream',
      body: `event: stage_started\ndata: ${JSON.stringify({ type: 'stage_started', run_id: 'run-new', stage: 'invoices', at: '2026-09-27T08:00:00Z', payload: {} })}\n\n`,
    },
    [`POST ${J}/cancel`]: { status: 200, body: { cancelled: true } },
  }
  await withHarness({ path: `/app/facturi/${JOB}`, routes }, async ({ page, requests }) => {
    await page.getByRole('heading', { name: 'Adaugă facturile' }).waitFor()
    const chooser = page.waitForEvent('filechooser')
    await page.getByRole('button', { name: 'Alege fişiere' }).click()
    await (
      await chooser
    ).setFiles({
      name: 'one.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('%PDF synthetic'),
    })
    await page.getByText('Citesc facturile').waitFor()
    await page.getByRole('button', { name: 'Opreşte' }).click()
    assert.ok(
      requests.some(
        (item) =>
          item.method === 'POST' &&
          item.path === `${J}/invoices/files` &&
          item.headers['content-type'].includes('multipart/form-data'),
      ),
    )
    assert.ok(
      requests.some((item) => item.method === 'POST' && item.path === `${J}/stages/invoices`),
    )
  })
})

test('M7 proposal, evidence, POD fill, mismatch and confirmation', async () => {
  let confirmed = false
  const routes = {
    ...invoiceRoutes,
    [`GET ${J}/invoices/identity`]: () => ({
      status: 200,
      body: confirmed ? acceptedIdentity : identity,
    }),
    [`GET ${J}/invoices`]: () => ({ status: 200, body: confirmed ? acceptedBatch : batch }),
    [`GET ${J}/export/checks`]: () => ({ status: 200, body: confirmed ? confirmedChecks : checks }),
    [`GET ${J}/log`]: () => ({ status: 200, body: confirmed ? [decision] : [] }),
    [`POST ${J}/invoices/identity`]: () => {
      confirmed = true
      return { status: 200, body: acceptedIdentity }
    },
    [`POST ${J}/log/${decision.id}/undo`]: () => {
      confirmed = false
      return { status: 200, body: decision }
    },
  }
  await withHarness({ path: `/app/facturi/${JOB}`, routes }, async ({ page, requests }) => {
    await page.getByRole('heading', { name: 'Al cui e acest lot?' }).waitFor()
    await page.getByText('DE CE ACEST CLIENT').waitFor()
    await page.getByText(/POD-ul se completează la 1 factură/).waitFor()
    await page.getByText('CE SE ÎNTÂMPLĂ CU CELELALTE FIŞIERE').waitFor()
    await page.getByText('Client: Exemplu Energie SA').waitFor()
    await page.getByRole('button', { name: 'Confirmă clientul' }).click()
    await page.getByRole('button', { name: 'Exportă Excel' }).waitFor()
    const sent = requests.find(
      (item) => item.method === 'POST' && item.path === `${J}/invoices/identity`,
    )
    assert.deepEqual(sent.body, { client_id: 'client-exemplu', on_revision: 1, confirm: true })
    await page.getByRole('button', { name: 'Anulează' }).click()
    await page.getByRole('heading', { name: 'Al cui e acest lot?' }).waitFor()
  })
  await withHarness(
    {
      path: `/app/facturi/${JOB}`,
      routes: {
        ...invoiceRoutes,
        [`GET ${J}/invoices/identity`]: {
          status: 200,
          body: { ...identity, candidate: { ...identity.candidate, cui: 'RO9999999' } },
        },
      },
    },
    async ({ page }) => {
      await page.getByText('Facturile par ale altui client').waitFor()
      assert.equal(await page.getByRole('button', { name: 'Confirmă clientul' }).count(), 0)
    },
  )
})

test('3f source, outlier, missing month, failed file exits and workbook', async () => {
  let exported = false
  let serverRevision = 1
  const routes = {
    ...invoiceRoutes,
    [`GET ${J}`]: () => ({ status: 200, body: { ...job, revision: serverRevision } }),
    [`GET ${J}/invoices/identity`]: { status: 200, body: acceptedIdentity },
    [`GET ${J}/invoices`]: { status: 200, body: acceptedBatch },
    [`GET ${J}/export/checks`]: { status: 200, body: confirmedChecks },
    [`GET ${J}/log`]: { status: 200, body: [decision] },
    [`GET ${J}/status`]: () => ({
      status: 200,
      body: exported
        ? {
            ...status,
            runs: [
              ready,
              {
                id: 'run-workbook-1',
                stage: 'invoices_workbook',
                state: 'ready',
                publication: 'current',
              },
            ],
          }
        : status,
    }),
    [`GET ${J}/outputs`]: () => ({ status: 200, body: exported ? [output] : [] }),
    [`POST ${J}/stages/invoices_workbook`]: () => {
      exported = true
      return {
        status: 202,
        body: { run_id: 'run-workbook-1', stage: 'invoices_workbook', state: 'running' },
      }
    },
    [`GET ${J}/events`]: {
      status: 200,
      contentType: 'text/event-stream',
      body: `event: stage_finished\ndata: ${JSON.stringify({ type: 'stage_finished', run_id: 'run-workbook-1', stage: 'invoices_workbook', at: '2026-09-27T08:00:00Z', payload: { publication: 'current' } })}\n\n`,
    },
    [`GET ${J}/outputs/${output.id}`]: {
      status: 200,
      body: 'PK synthetic workbook',
      contentType: output.media_type,
    },
    [`POST ${J}/invoices/files?replace=invoices%2F0013`]: {
      status: 200,
      body: {
        added: [{ slot: 'invoices/0013', file_name: 'retry.pdf', sha: 'sha-retry' }],
        rejected: [],
      },
    },
    [`POST ${J}/stages/invoices`]: {
      status: 202,
      body: { run_id: 'run-read-2', stage: 'invoices', state: 'running' },
    },
    [`DELETE ${J}/slots/invoices%2F0013/versions/1`]: { status: 200, body: { deleted: true } },
  }
  await withHarness({ path: `/app/facturi/${JOB}`, routes }, async ({ page, requests }) => {
    await page.getByRole('button', { name: 'Exportă Excel' }).waitFor()
    await page.getByText('12,00').waitFor()
    await page.getByText('9 600,00').waitFor()
    await page.getByText('0,8000').first().waitFor()
    await page.getByText('factura lipseşte').waitFor()
    assert.equal(await page.getByRole('row').filter({ hasText: 'factura lipseşte' }).count(), 1)
    await page.getByRole('button', { name: 'Adaug-o' }).waitFor()
    await page.getByText(/Fişierul e o scanare fără text şi la 110 dpi/).waitFor()
    await page.getByRole('list', { name: 'Starea fişierelor' }).getByText('bad.pdf').waitFor()
    await page.getByRole('button', { name: 'Vezi octombrie' }).click()
    await page.getByText('DE CE E MARCATĂ').waitFor()
    await page.locator('.invoice-open mark').getByText('2000').waitFor()
    assert.ok(
      requests.some(
        (item) =>
          item.path === `${J}/invoices/page.png?slot=invoices%2F0010&page=1&crop=active_energy`,
      ),
    )
    assert.equal(
      requests.some((item) => item.path.includes('/anomaly')),
      false,
    )
    serverRevision = 2
    await page.getByRole('button', { name: 'Exportă Excel' }).click()
    assert.equal(
      requests.find((item) => item.path === `${J}/stages/invoices_workbook`)?.body.on_revision,
      1,
    )
    await page.getByRole('button', { name: 'Descarcă Excel' }).waitFor()
    await page.getByRole('button', { name: 'Descarcă Excel' }).click()
    assert.ok(requests.some((item) => item.path === `${J}/outputs/${output.id}`))
    const chooser = page.waitForEvent('filechooser')
    await page.getByRole('button', { name: 'Reîncarcă' }).click()
    await (
      await chooser
    ).setFiles({
      name: 'retry.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('%PDF synthetic'),
    })
    await page.getByText('Citesc facturile').waitFor()
    assert.ok(requests.some((item) => item.path === `${J}/invoices/files?replace=invoices%2F0013`))
  })
})

test('table explains blocked export and removes a failed invoice with its slot revision', async () => {
  const routes = {
    ...invoiceRoutes,
    [`GET ${J}/invoices/identity`]: { status: 200, body: acceptedIdentity },
    [`GET ${J}/invoices`]: { status: 200, body: acceptedBatch },
    [`GET ${J}/export/checks`]: { status: 200, body: checks },
    [`DELETE ${J}/slots/invoices%2F0013/versions/1`]: {
      status: 200,
      body: { deleted: true },
    },
    [`POST ${J}/stages/invoices`]: {
      status: 202,
      body: { run_id: 'run-read-3', stage: 'invoices', state: 'running' },
    },
    [`GET ${J}/events`]: { status: 200, contentType: 'text/event-stream', body: '' },
  }
  await withHarness({ path: `/app/facturi/${JOB}`, routes }, async ({ page, requests }) => {
    const exportButton = page.getByRole('button', { name: 'Exportă Excel' })
    await exportButton.waitFor()
    assert.equal(await exportButton.isDisabled(), true)
    assert.equal(await exportButton.getAttribute('title'), 'Clientul lotului nu este confirmat.')
    await page.getByRole('button', { name: 'Scoate' }).click()
    await page.getByText('Citesc facturile').waitFor()
    const removed = requests.find(
      (item) => item.method === 'DELETE' && item.path === `${J}/slots/invoices%2F0013/versions/1`,
    )
    assert.deepEqual(removed.body, { confirm: true, on_revision: 2 })
  })
})
