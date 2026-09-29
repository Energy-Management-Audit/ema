// The builder's D11 behaviour tests on the synthetic fixture.

import assert from 'node:assert/strict'
import test from 'node:test'
import {
  FINAL_CHECKS,
  EXPORTED,
  FINAL_OUTPUTS,
  JOB,
  READY_CHECKS,
  eventStream,
} from '../fixtures/piee/default.mjs'
import { problem } from './harness.mjs'
import { count, settle, withHarness } from './helpers.mjs'

const J = `/jobs/${JOB}`

test('B18 S6 X1: the package waits for final_ok; then it starts piee_word', async () => {
  await withHarness({ path: `/app/piee/${JOB}/predare` }, async ({ page }) => {
    const button = page.getByRole('button', { name: 'Generează pachetul' })
    await button.waitFor()
    assert.equal(await button.isDisabled(), true)
    await page.getByText('Conflict: Date anuale total tep').waitFor()
  })
  await withHarness(
    {
      path: `/app/piee/${JOB}/predare`,
      routes: {
        [`GET ${J}/export/checks`]: { status: 200, body: READY_CHECKS },
        [`POST ${J}/stages/piee_word`]: {
          status: 202,
          body: { run_id: 'run-word-2', stage: 'piee_word', state: 'running' },
        },
        [`GET ${J}/events`]: {
          status: 200,
          contentType: 'text/event-stream',
          body: eventStream([]),
        },
      },
    },
    async ({ page, requests }) => {
      await page.getByRole('button', { name: 'Generează pachetul' }).click()
      await settle(page)
      assert.deepEqual(requests.find((item) => item.path === `${J}/stages/piee_word`).body, {
        on_revision: 7,
      })
    },
  )
})

test('B19 B20 B21 S6 X3/X4: approving binds the listed final and the readiness shown', async () => {
  const routes = {
    [`GET ${J}/outputs`]: { status: 200, body: FINAL_OUTPUTS },
    [`GET ${J}/export/checks`]: { status: 200, body: FINAL_CHECKS },
    [`POST ${J}/export`]: { status: 200, body: EXPORTED },
  }
  await withHarness(
    { path: `/app/piee/${JOB}/predare`, routes },
    async ({ page, requests, setRoute }) => {
      await page.getByTestId('package-file-out-final-1').waitFor()
      await page.getByTestId('package-file-out-pdf-1').waitFor()
      await settle(page)
      const before = requests.length
      setRoute(`GET ${J}/approvals`, {
        status: 200,
        body: [
          {
            id: 'a-1',
            job_id: JOB,
            output_id: 'out-final-1',
            readiness_hash: 'hash-ready',
            on_decision: null,
            at: new Date().toISOString(),
            actor: 'user',
          },
        ],
      })
      await page.getByRole('button', { name: 'Aprobă şi exportă' }).click()
      await page.getByText(`Fişierele finale sunt în ${EXPORTED.folder}`).waitFor()
      assert.deepEqual(requests[before].method + ' ' + requests[before].path, `POST ${J}/export`)
      assert.deepEqual(requests[before].body, {
        dest_dir: null,
        output_id: 'out-final-1',
        readiness_hash: 'hash-ready',
        confirm: true,
      })
      await page.getByText(/Aprobat acum/).waitFor()
      assert.equal(await page.getByRole('button', { name: 'Aprobă şi exportă' }).count(), 0)
    },
  )
  await withHarness(
    {
      path: `/app/piee/${JOB}/predare`,
      routes: {
        ...routes,
        [`POST ${J}/export`]: problem(
          'hash_mismatch',
          403,
          'Versiunea de pregătire nu corespunde.',
        ),
      },
    },
    async ({ page, requests }) => {
      await page.getByRole('button', { name: 'Aprobă şi exportă' }).click()
      await page
        .getByText('Datele s-au schimbat de când ai deschis pagina. Verifică din nou.')
        .waitFor()
      await page.getByText('Versiunea de pregătire nu corespunde.').waitFor()
      await settle(page)
      assert.equal(count(requests, 'POST', `${J}/export`), 1)
      assert.ok(count(requests, 'GET', `${J}/approvals`) >= 2)
    },
  )
})

test('B23 the preview opens only the same-run PDF, as a blob', async () => {
  await withHarness({ path: `/app/piee/${JOB}/date` }, async ({ page }) => {
    await page.getByTestId('carrier-table-electricity_grid').waitFor()
    assert.equal(await page.getByRole('button', { name: 'Previzualizare' }).isDisabled(), true)
  })
  const noPdf = FINAL_OUTPUTS.filter((item) => item.id !== 'out-pdf-1')
  await withHarness(
    {
      path: `/app/piee/${JOB}/date`,
      routes: {
        [`GET ${J}/outputs`]: { status: 200, body: noPdf },
        [`GET ${J}/export/checks`]: { body: FINAL_CHECKS },
      },
    },
    async ({ page }) => {
      await page.getByTestId('carrier-table-electricity_grid').waitFor()
      await settle(page)
      assert.equal(await page.getByRole('button', { name: 'Previzualizare' }).isDisabled(), true)
    },
  )
  await withHarness(
    {
      path: `/app/piee/${JOB}/date`,
      routes: {
        [`GET ${J}/outputs`]: { status: 200, body: FINAL_OUTPUTS },
        [`GET ${J}/export/checks`]: { body: FINAL_CHECKS },
      },
    },
    async ({ page, requests }) => {
      await page.getByTestId('carrier-table-electricity_grid').waitFor()
      await page.evaluate(() => {
        const original = window.open.bind(window)
        window.__opened = []
        window.open = (url, ...rest) => {
          window.__opened.push(String(url))
          return original(url, ...rest)
        }
      })
      await page.getByRole('button', { name: 'Previzualizare' }).click()
      await page.waitForFunction(() => window.__opened.length > 0)
      const [opened] = await page.evaluate(() => window.__opened)
      assert.ok(opened.startsWith('blob:'), opened)
      const fetched = requests.find((item) => item.path === `${J}/outputs/out-pdf-1`)
      assert.equal(fetched.resourceType, 'fetch')
      assert.equal(requests.filter((item) => item.path.includes('preview.pdf')).length, 0)
    },
  )
})

test('B24 a closed session shows E3', async () => {
  await withHarness(
    {
      path: `/app/piee/${JOB}/date`,
      routes: { [`GET ${J}/fields`]: problem('session_required', 403, 'Sesiunea este necesară.') },
    },
    async ({ page }) => {
      await page.getByText('Sesiunea s-a închis').waitFor()
      await page.getByText('Porneşte Ema din nou ca să continui.').waitFor()
    },
  )
})

test('B25 B26 no horizontal page scroll at 1280×800; no image evidence requests', async () => {
  await withHarness(
    {
      path: `/app/piee/${JOB}/date`,
      viewport: { width: 1280, height: 800 },
      routes: {
        [`GET ${J}/outputs`]: { status: 200, body: FINAL_OUTPUTS },
        [`GET ${J}/export/checks`]: { body: FINAL_CHECKS },
      },
    },
    async ({ page, requests }) => {
      for (const tab of ['documente', 'date', 'masuri', 'jurnal', 'predare']) {
        await page.evaluate((path) => {
          history.pushState(null, '', path)
          window.dispatchEvent(new PopStateEvent('popstate'))
        }, `/app/piee/${JOB}/${tab}`)
        await settle(page)
        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth - window.innerWidth,
        )
        assert.ok(overflow <= 0, `${tab}: ${String(overflow)}`)
      }
      assert.equal(
        requests.filter((item) => /\/evidence\/.*\/(snippet|page)\.png/.test(item.path)).length,
        0,
      )
    },
  )
})
