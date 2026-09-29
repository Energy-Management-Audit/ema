// The builder's D11 behaviour tests on the synthetic fixture.

import assert from 'node:assert/strict'
import test from 'node:test'
import { JOB, OUTPUTS, eventStream } from '../fixtures/piee/default.mjs'
import { problem } from './harness.mjs'
import { count, settle, withHarness } from './helpers.mjs'

const J = `/jobs/${JOB}`

test('B12 B13 generating: progress, terminal refetch, other runs ignored, stop, failure', async () => {
  const stream = eventStream([
    {
      run_id: 'run-other',
      stage: 'piee_word',
      type: 'stage_progress',
      payload: { done: 5, total: 9, message: 'Altceva' },
    },
    {
      run_id: 'run-gen-2',
      stage: 'piee_generate',
      type: 'stage_started',
      payload: { state: 'running' },
    },
    {
      run_id: 'run-gen-2',
      stage: 'piee_generate',
      type: 'stage_progress',
      payload: { done: 1, total: 2, message: 'Ciornă generată' },
    },
  ])
  await withHarness(
    {
      path: `/app/piee/${JOB}/date`,
      routes: {
        [`POST ${J}/piee/generate`]: {
          status: 202,
          body: { run_id: 'run-gen-2', stage: 'piee_generate', state: 'running' },
        },
        [`GET ${J}/events`]: { status: 200, contentType: 'text/event-stream', body: stream },
        [`POST ${J}/cancel`]: { status: 200, body: { cancelled: true } },
      },
    },
    async ({ page, requests, setRoute }) => {
      await page.getByTestId('carrier-table-electricity_grid').waitFor()
      await page.getByRole('button', { name: 'Generează programul' }).click()
      const panel = page.getByTestId('run-panel')
      await panel.getByText('Ciornă generată').waitFor()
      assert.match(await panel.innerText(), /Se lucrează/)
      assert.match(await panel.innerText(), /1\/2/)
      assert.doesNotMatch(await panel.innerText(), /Altceva/)
      const post = requests.find((item) => item.path === `${J}/piee/generate`)
      assert.deepEqual(post.body, { kind: 'draft', on_revision: 7 })
      await panel.getByRole('button', { name: 'Opreşte' }).click()
      await settle(page)
      assert.equal(count(requests, 'POST', `${J}/cancel`), 1)
      const before = count(requests, 'GET', `${J}/outputs`)
      setRoute(`GET ${J}/events`, {
        status: 200,
        contentType: 'text/event-stream',
        body: eventStream([
          {
            run_id: 'run-gen-2',
            stage: 'piee_generate',
            type: 'stage_progress',
            payload: { done: 2, total: 2, message: 'Prelucrare date generată' },
          },
          {
            run_id: 'run-gen-2',
            stage: 'piee_generate',
            type: 'stage_finished',
            payload: { state: 'ready', publication: 'current', item_failures: 0, warnings: 0 },
          },
        ]),
      })
      await page.getByTestId('run-panel').waitFor({ state: 'detached', timeout: 15_000 })
      await settle(page)
      for (const path of [
        '',
        '/status',
        '/outputs',
        '/fields',
        '/fields?status=missing',
        '/export/checks',
        '/piee/summary',
        '/log',
      ]) {
        assert.ok(count(requests, 'GET', `${J}${path}`) >= 2, path)
      }
      assert.ok(count(requests, 'GET', `${J}/outputs`) > before)
    },
  )
  const failed = {
    id: JOB,
    type: 'piee',
    state: 'failed',
    revision: 9,
    runs: [{ id: 'run-gen-3', stage: 'piee_generate', state: 'failed', error: 'Etapa a eşuat.' }],
  }
  await withHarness(
    {
      path: `/app/piee/${JOB}/date`,
      routes: { [`GET ${J}/status`]: { status: 200, body: failed } },
    },
    async ({ page }) => {
      const panel = page.getByTestId('run-failed')
      await panel.waitFor()
      assert.match(await panel.innerText(), /Generarea nu s-a încheiat/)
      await panel.getByRole('button', { name: 'Încearcă din nou' }).waitFor()
    },
  )
})

test('B14 an existing draft generates directly without an external-edit dialog', async () => {
  await withHarness(
    {
      path: `/app/piee/${JOB}/date`,
      routes: {
        [`GET ${J}/outputs`]: { status: 200, body: OUTPUTS },
        [`POST ${J}/piee/generate`]: {
          status: 202,
          body: { run_id: 'run-gen-4', stage: 'piee_generate', state: 'running' },
        },
        [`GET ${J}/events`]: {
          status: 200,
          contentType: 'text/event-stream',
          body: eventStream([]),
        },
      },
    },
    async ({ page, requests }) => {
      await page.getByTestId('carrier-table-electricity_grid').waitFor()
      await page.getByRole('button', { name: 'Generează programul' }).click()
      assert.equal(await page.getByRole('dialog').count(), 0)
      await settle(page)
      assert.equal(count(requests, 'POST', `${J}/piee/generate`), 1)
    },
  )
})

test('B15 S4: summary tiles, groups, chips, and the term editor', async () => {
  await withHarness(
    {
      path: `/app/piee/${JOB}/masuri`,
      routes: {
        [`POST ${J}/fields/f-term-p2/decide`]: {
          status: 200,
          body: {
            id: 'd-11',
            at: '2026-09-25T09:00:00Z',
            actor: 'user',
            field_id: 'f-term-p2',
            on_revision: 1,
            action: 'correct',
            before: {},
            after: {},
          },
        },
      },
    },
    async ({ page, requests }) => {
      await page.getByTestId('annual-check').waitFor()
      assert.match(await page.locator('.ema-count-bar').first().innerText(), /5 \/ 7/)
      assert.match(await page.getByTestId('kpi-savings').innerText(), /840/)
      assert.match(await page.getByTestId('kpi-investment').innerText(), /660/)
      assert.match(await page.getByTestId('kpi-total').innerText(), /22 164,05/)
      assert.equal(await page.getByTestId('annual-check').getAttribute('data-state'), 'mismatch')
      const titles = await page.locator('.measure-group__title').allInnerTexts()
      assert.deepEqual(titles, ['SOLUTII EE PLANIFICATE', 'SOLUTII EE', 'AUDIT ENERGETIC'])
      await page
        .getByTestId('measure-row-measure.planned.1')
        .getByText('Anexa 2–3 · Solutii EE planificate')
        .waitFor()
      await page.getByRole('button', { name: 'Completează termenele' }).click()
      const row = page.getByTestId('measure-row-measure.planned.2')
      const editor = row.getByRole('textbox')
      await editor.waitFor()
      assert.equal(await editor.evaluate((node) => node === document.activeElement), true)
      await editor.fill('2027')
      await row.getByRole('button', { name: 'Salvează' }).click()
      await settle(page)
      const post = requests.find((item) => item.path === `${J}/fields/f-term-p2/decide`)
      assert.equal(post.body.value, '2027')
      assert.equal(post.body.action, 'correct')
    },
  )
})

test('B16 B17 S2: slots, outputs by blob, and the upload dialog', async () => {
  await withHarness(
    {
      path: `/app/piee/${JOB}/documente`,
      routes: {
        [`POST /clients/client-exemplu/files`]: {
          status: 201,
          body: {
            sha: 'sha-new',
            name: 'nou.xlsx',
            size_bytes: 10,
            kind: 'xlsx',
            intake: 'stored',
          },
        },
        [`POST ${J}/prelucrare`]: { status: 200, body: { authority: 'input_for_covered_years' } },
        [`PUT ${J}/slots/anexa`]: {
          status: 200,
          body: {
            job_id: JOB,
            slot: 'anexa',
            version: 2,
            file_sha: 'sha-new',
            origin: 'upload',
            converted_from: null,
          },
        },
      },
    },
    async ({ page, requests, setRoute }) => {
      await page
        .getByTestId('slot-row-anexa')
        .getByText('Anexa 2 si 3 consum 2025 - Exemplu.xlsx')
        .waitFor()
      assert.equal(await page.locator('[data-testid^="slot-row-"]').count(), 4)
      assert.match(await page.getByTestId('slot-row-prelucrare').innerText(), /acoperă 2023–2025/)
      assert.match(await page.getByTestId('slot-row-prelucrare').innerText(), /3,2 MB/)
      await page.evaluate(() => {
        const created = []
        window.__blobs = created
        const original = URL.createObjectURL
        URL.createObjectURL = (blob) => {
          const url = original(blob)
          created.push(url)
          return url
        }
      })
      await page
        .getByTestId('output-row-out-draft-1')
        .getByRole('button', { name: 'Descarcă' })
        .click()
      await settle(page)
      const fetched = requests.find((item) => item.path === `${J}/outputs/out-draft-1`)
      assert.equal(fetched.resourceType, 'fetch')
      assert.ok((await page.evaluate(() => window.__blobs))[0].startsWith('blob:'))

      const upload = async (slot) => {
        await page.getByTestId('upload-input').setInputFiles({
          name: 'nou.xlsx',
          mimeType: 'application/vnd.ms-excel',
          buffer: Buffer.from('PK'),
        })
        const dialog = page.getByRole('dialog')
        await dialog.getByText('Unde intră fişierul?').waitFor()
        assert.equal(await dialog.getByRole('button', { name: 'Adaugă' }).isDisabled(), true)
        await dialog.getByText(slot, { exact: true }).click()
        await dialog.getByRole('button', { name: 'Adaugă' }).click()
      }
      await upload('Prelucrare date')
      await page.getByRole('dialog').waitFor({ state: 'detached' })
      const multipart = requests.find((item) => item.path === '/clients/client-exemplu/files')
      assert.match(multipart.headers['content-type'], /multipart\/form-data/)
      assert.deepEqual(
        requests.find((item) => item.path === `${J}/prelucrare` && item.method === 'POST').body,
        { file_id: 'sha-new', role: 'input' },
      )
      await upload('Anexa 2–3')
      await page.getByRole('dialog').waitFor({ state: 'detached' })
      assert.deepEqual(requests.find((item) => item.method === 'PUT').body, { file_sha: 'sha-new' })
      setRoute(
        'POST /clients/client-exemplu/files',
        problem('file_type', 415, 'Tipul fişierului este invalid.'),
      )
      await upload('Anexa 2–3')
      await page.getByRole('dialog').getByText('Tipul fişierului este invalid.').waitFor()
    },
  )
})

test('B22 S5: newest first, undo, undone entries', async () => {
  await withHarness(
    {
      path: `/app/piee/${JOB}/jurnal`,
      routes: {
        [`POST ${J}/log/d-1/undo`]: {
          status: 200,
          body: {
            id: 'd-12',
            at: '2026-09-25T09:00:00Z',
            actor: 'user',
            field_id: 'f-cui',
            on_revision: 2,
            action: 'undo',
            before: {},
            after: {},
          },
        },
      },
    },
    async ({ page, requests }) => {
      const journal = page.locator('.journal')
      await journal.getByTestId('journal-entry-d-1').waitFor()
      const ids = await journal
        .locator('[data-testid^="journal-entry-"]')
        .evaluateAll((nodes) => nodes.map((node) => node.dataset.testid))
      assert.deepEqual(ids, ['journal-entry-d-3', 'journal-entry-d-2', 'journal-entry-d-1'])
      const undone = journal.getByTestId('journal-entry-d-2')
      assert.match(await undone.innerText(), /· anulat/)
      assert.equal(await undone.getByRole('button', { name: 'Anulează' }).count(), 0)
      await journal
        .getByTestId('journal-entry-d-1')
        .getByRole('button', { name: 'Anulează' })
        .click()
      await settle(page)
      assert.equal(count(requests, 'POST', `${J}/log/d-1/undo`), 1)
    },
  )
})
