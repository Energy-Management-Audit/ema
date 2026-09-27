import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { CLIENT, DOCUMENTS, FIELDS, JOB, routes } from '../fixtures/audit/default.mjs'
import { eventStream } from '../fixtures/piee/default.mjs'
import { withHarness } from './helpers.mjs'

const J = `/jobs/${JOB.id}`

test('document errors have recovery actions and Scoate uses the slot revision', async () => {
  const slot = 'dossier/3. Protejat.pdf'
  const documents = structuredClone(DOCUMENTS)
  documents.files.find((file) => file.slot === slot).slot_revision = 7
  await withHarness(
    {
      path: `/app/audit/${JOB.id}/documente`,
      routes: {
        ...routes,
        [`GET ${J}/audit/documents`]: { body: documents },
        [`DELETE ${J}/slots/${encodeURIComponent(slot)}/versions/1`]: { body: { deleted: true } },
        [`POST /clients/${CLIENT.id}/files`]: { body: { sha: 'replacement-sha' } },
        [`PUT ${J}/slots/dossier/1.%20Facturi.pdf`]: { body: { version: 2 } },
      },
    },
    async ({ page, requests }) => {
      await page
        .getByText('Protejat cu parolă — Ema nu l-a putut deschide. Nu intră în audit.')
        .waitFor()
      const row = page.locator('.audit-doc-row').filter({ hasText: '3. Protejat.pdf' })
      const deleting = page.waitForResponse((response) => response.request().method() === 'DELETE')
      await row.getByRole('button', { name: 'Scoate' }).click()
      await deleting
      const removed = requests.find((item) => item.method === 'DELETE')
      assert.deepEqual(removed.body, { confirm: true, on_revision: 7 })
      assert.equal(
        requests.some((item) => item.path.includes('/versions') && item.method === 'GET'),
        false,
      )
      const failed = page.locator('.audit-doc-row').filter({ hasText: '1. Facturi.pdf' })
      assert.equal(await failed.getByRole('button', { name: 'Reîncarcă' }).count(), 1)
      await failed.locator('input[type=file]').setInputFiles({
        name: 'replacement.pdf',
        mimeType: 'application/pdf',
        buffer: Buffer.from('synthetic replacement'),
      })
      await page.waitForResponse(
        (response) =>
          response.url().includes('/slots/dossier/1.%20Facturi.pdf') &&
          response.request().method() === 'PUT',
      )
      assert.deepEqual(
        requests.find((item) => item.path === `${J}/slots/dossier/1.%20Facturi.pdf`).body,
        { file_sha: 'replacement-sha' },
      )
      await page.getByRole('button', { name: 'Adaugă documente' }).first().click()
      await page.getByRole('dialog', { name: 'Unde intră fişierele?' }).waitFor()
      await page.getByText('Fotografii din vizită', { exact: true }).click()
      const picker = page.getByRole('dialog').locator('input[type=file]')
      assert.equal(await picker.getAttribute('webkitdirectory'), '')
    },
  )
})

test('document next step and accepted-field rerun are explicit', async () => {
  const stale = structuredClone(DOCUMENTS)
  stale.runs.read.current = false
  await withHarness(
    {
      path: `/app/audit/${JOB.id}/documente`,
      routes: {
        ...routes,
        [`GET ${J}/audit/documents`]: { body: stale },
        [`GET ${J}/fields`]: { body: [{ ...FIELDS[0], review: 'accepted' }] },
        [`POST ${J}/stages/read`]: { body: { run_id: 'run-read' } },
      },
    },
    async ({ page, requests }) => {
      await page.getByRole('button', { name: 'Extrage datele' }).click()
      await page.getByRole('dialog', { name: 'Reiei extragerea?' }).waitFor()
      assert.equal(
        requests.some((item) => item.path === `${J}/stages/read`),
        false,
      )
      await page.getByRole('button', { name: 'Renunţă' }).click()
      await page.getByRole('button', { name: 'Extrage datele' }).click()
      await page.getByRole('button', { name: 'Reia extragerea' }).click()
      assert.deepEqual(requests.find((item) => item.path === `${J}/stages/read`).body, {
        on_revision: JOB.revision,
      })
    },
  )
})

test('upload dialog sends each dossier file to its own slot and continues after a failure', async () => {
  let upload = 0
  await withHarness(
    {
      path: `/app/audit/${JOB.id}/documente`,
      routes: {
        ...routes,
        [`POST /clients/${CLIENT.id}/files`]: () => ({ body: { sha: `sha-${++upload}` } }),
        [`PUT ${J}/slots/dossier/first.pdf`]: { body: { version: 1 } },
        [`PUT ${J}/slots/dossier/second.pdf`]: { body: { version: 1 } },
      },
    },
    async ({ page, requests }) => {
      await page.getByRole('button', { name: 'Adaugă documente' }).first().click()
      await page
        .getByRole('dialog')
        .locator('input[type=file]')
        .setInputFiles([
          { name: 'first.pdf', mimeType: 'application/pdf', buffer: Buffer.from('first') },
          { name: 'second.pdf', mimeType: 'application/pdf', buffer: Buffer.from('second') },
        ])
      await page.getByRole('dialog').getByRole('button', { name: 'Adaugă documente' }).click()
      await page.getByRole('dialog').waitFor({ state: 'hidden' })
      assert.deepEqual(
        requests
          .filter((item) => item.method === 'PUT' && item.path.includes('/slots/'))
          .map((item) => item.path),
        [`${J}/slots/dossier/first.pdf`, `${J}/slots/dossier/second.pdf`],
      )
    },
  )
})

test('scanned copy follows OCR setting; two visit panels and the measures form are available', async () => {
  const off = {
    ...routes['GET /settings'].body,
    extraction: { ...routes['GET /settings'].body.extraction, ocr: false },
  }
  await withHarness(
    {
      path: `/app/audit/${JOB.id}/documente`,
      routes: {
        ...routes,
        'GET /settings': { body: off },
        'GET /audit/forms/masuri-propuse.xlsx': {
          body: 'synthetic workbook',
          contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        },
      },
    },
    async ({ page, requests }) => {
      await page
        .getByText('Text scanat — nu s-a putut citi nimic. Originalul rămâne neatins.')
        .waitFor()
      await page.getByRole('button', { name: /Imagini tehnice/ }).click()
      await page.getByText('Contoare şi tablouri — Panel A').waitFor()
      await page.getByText('Contoare şi tablouri — Panel B').waitFor()
      const download = page.waitForEvent('download')
      await page.getByRole('button', { name: 'Descarcă formularul' }).click()
      assert.equal((await download).suggestedFilename(), 'masuri-propuse.xlsx')
      assert.ok(requests.some((item) => item.path === '/audit/forms/masuri-propuse.xlsx'))
    },
  )
})

test('document activity shows terminal runs and opens the files to verify', async () => {
  await withHarness(
    {
      path: `/app/audit/${JOB.id}/documente`,
      routes: {
        ...routes,
        [`GET ${J}/status`]: {
          body: {
            id: JOB.id,
            type: 'audit',
            state: 'open',
            revision: 1,
            runs: [
              {
                id: 'run-1',
                stage: 'intake',
                state: 'ready',
                started_at: '2026-09-27T08:00:00Z',
                ended_at: '2026-09-27T08:01:00Z',
              },
            ],
          },
        },
      },
    },
    async ({ page }) => {
      await page.getByText('Dosarul citit').waitFor()
      await page.getByText('Verifică 4 documente').waitFor()
      await page.getByRole('button', { name: 'Rezolvă acum' }).click()
      assert.equal(
        await page.getByRole('button', { name: /De verificat/ }).getAttribute('aria-pressed'),
        'true',
      )
      assert.equal(
        await page.locator('.audit-doc-row').filter({ hasText: '0. Necesar info.xlsx' }).count(),
        0,
      )
    },
  )
})

test('visit folder upload uses its first child as the meter panel', async () => {
  const folder = mkdtempSync(join(tmpdir(), 'ema-visit-'))
  mkdirSync(join(folder, 'Panel A'))
  writeFileSync(join(folder, 'Panel A', 'one.jpg'), 'synthetic photo')
  try {
    await withHarness(
      {
        path: `/app/audit/${JOB.id}/documente`,
        routes: {
          ...routes,
          [`POST /clients/${CLIENT.id}/files`]: { body: { sha: 'visit-sha' } },
          [`PUT ${J}/slots/visit/meter/Panel%20A/one.jpg`]: { body: { version: 1 } },
        },
      },
      async ({ page, requests }) => {
        await page.getByRole('button', { name: 'Adaugă documente' }).first().click()
        await page.getByText('Fotografii din vizită', { exact: true }).click()
        await page.getByRole('dialog').locator('input[type=file]').setInputFiles(folder)
        await page.getByRole('dialog').getByRole('button', { name: 'Adaugă documente' }).click()
        await page.getByRole('dialog').waitFor({ state: 'hidden' })
        assert.ok(requests.some((item) => item.path === `${J}/slots/visit/meter/Panel%20A/one.jpg`))
      },
    )
  } finally {
    rmSync(folder, { recursive: true, force: true })
  }
})

test('upload lists one file failure and still assigns the next file', async () => {
  let uploads = 0
  await withHarness(
    {
      path: `/app/audit/${JOB.id}/documente`,
      routes: {
        ...routes,
        [`POST /clients/${CLIENT.id}/files`]: () =>
          ++uploads === 1
            ? {
                status: 415,
                body: {
                  type: 'urn:ema:error:file_type',
                  title: 'Tipul fişierului nu este acceptat.',
                  status: 415,
                },
              }
            : { body: { sha: 'second-sha' } },
        [`PUT ${J}/slots/dossier/second.pdf`]: { body: { version: 1 } },
      },
    },
    async ({ page, requests }) => {
      await page.getByRole('button', { name: 'Adaugă documente' }).first().click()
      await page
        .getByRole('dialog')
        .locator('input[type=file]')
        .setInputFiles([
          { name: 'first.pdf', mimeType: 'application/pdf', buffer: Buffer.from('first') },
          { name: 'second.pdf', mimeType: 'application/pdf', buffer: Buffer.from('second') },
        ])
      await page.getByRole('dialog').getByRole('button', { name: 'Adaugă documente' }).click()
      await page.getByText(/first\.pdf: Tipul fişierului nu este acceptat\./).waitFor()
      assert.ok(requests.some((item) => item.path === `${J}/slots/dossier/second.pdf`))
      assert.equal(
        requests.some((item) => item.path === `${J}/slots/dossier/first.pdf`),
        false,
      )
    },
  )
})

test('a single-file form refuses multiple files instead of dropping one', async () => {
  await withHarness(
    { path: `/app/audit/${JOB.id}/documente`, routes },
    async ({ page, requests }) => {
      await page.locator('.audit-drop').evaluate((node) => {
        const transfer = new DataTransfer()
        transfer.items.add(new File(['one'], 'one.pdf', { type: 'application/pdf' }))
        transfer.items.add(new File(['two'], 'two.pdf', { type: 'application/pdf' }))
        node.dispatchEvent(new DragEvent('drop', { bubbles: true, dataTransfer: transfer }))
      })
      const dialog = page.getByRole('dialog')
      await dialog.getByText('Anexa 2–3').click()
      await dialog.getByRole('button', { name: 'Adaugă documente' }).click()
      await dialog.getByText('Alege un singur fişier pentru acest formular.').waitFor()
      assert.equal(
        requests.some((item) => item.method === 'POST' && item.path.includes('/files')),
        false,
      )
    },
  )
})

test('document stage shows run progress and offers stop', async () => {
  const stale = structuredClone(DOCUMENTS)
  stale.runs.read.current = false
  await withHarness(
    {
      path: `/app/audit/${JOB.id}/documente`,
      routes: {
        ...routes,
        [`GET ${J}/audit/documents`]: { body: stale },
        [`POST ${J}/stages/read`]: {
          status: 202,
          body: { run_id: 'audit-read', stage: 'read', state: 'running' },
        },
        [`GET ${J}/events`]: {
          contentType: 'text/event-stream',
          body: eventStream([
            {
              run_id: 'audit-read',
              stage: 'read',
              type: 'stage_progress',
              payload: { done: 2, total: 4, message: 'Citeşte documente' },
            },
          ]),
        },
        [`POST ${J}/cancel`]: { body: { cancelled: true } },
      },
    },
    async ({ page, requests }) => {
      await page.getByRole('button', { name: 'Extrage datele' }).click()
      await page.getByText('Citeşte documente').waitFor()
      assert.equal(await page.locator('.audit-run__steps li').count(), 1)
      await page.locator('.audit-run__steps').getByText('2/4').waitFor()
      await page.getByRole('button', { name: 'Opreşte' }).click()
      await page.waitForResponse((response) => response.url().endsWith(`${J}/cancel`))
      assert.ok(requests.some((item) => item.method === 'POST' && item.path === `${J}/cancel`))
    },
  )
})
