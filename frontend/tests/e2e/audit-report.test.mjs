// 3d Raport Word on the synthetic audit fixture (D6, D10 frontend).

import assert from 'node:assert/strict'
import test from 'node:test'
import {
  DRAFT_RUN,
  J,
  JOB,
  OUTPUTS,
  REPORT,
  eventStream,
  reportRoutes,
} from '../fixtures/audit-report/default.mjs'
import { problem } from './harness.mjs'
import { count, settle, withHarness } from './helpers.mjs'

const path = `/app/audit/${JOB}/raport`
const started = {
  status: 202,
  body: { run_id: 'run-draft-2', stage: 'audit_render', state: 'running' },
}
const progress = [
  {
    run_id: 'run-draft-2',
    stage: 'audit_render',
    type: 'stage_started',
    payload: { state: 'running' },
  },
  {
    run_id: 'run-draft-2',
    stage: 'audit_render',
    type: 'stage_progress',
    payload: { done: 3, total: 7, message: 'Capitolul 4 din 7 — Analiza consumurilor' },
  },
]

test('the preview renders every PDF page from a fetch, and CUPRINS jumps to a page', async () => {
  await withHarness({ path, routes: reportRoutes }, async ({ page, requests }) => {
    const pages = page.getByTestId('pdf-page')
    await page.getByTestId('pdf-pages').waitFor()
    assert.equal(await pages.count(), 3)
    await page.locator('.report-page__canvas').first().waitFor()
    const fetched = requests.filter((item) => item.path === `${J}/outputs/out-draft-pdf`)
    assert.equal(fetched.length, 1)
    assert.equal(fetched[0].resourceType, 'fetch')
    assert.equal(await page.locator('iframe, embed, object').count(), 0)
    const toc = page.getByTestId('report-toc')
    assert.equal(await toc.locator('[data-state="done"]').count(), 6)
    await toc.getByRole('button', { name: /^4 · Analiza/ }).click()
    await page.waitForFunction(() => {
      const frame = document.querySelectorAll('[data-testid="pdf-page"]')[2]
      const box = frame.getBoundingClientRect()
      return box.top >= 0 && box.top < 400
    })
    const background = await pages
      .first()
      .evaluate((node) => getComputedStyle(node).backgroundColor)
    assert.equal(background, 'rgb(255, 253, 246)')
  })
})

test('Generează ciorna starts audit_render, shows progress, stops, and refetches when done', async () => {
  await withHarness(
    {
      path,
      routes: {
        ...reportRoutes,
        [`POST ${J}/stages/audit_render`]: started,
        [`GET ${J}/events`]: {
          status: 200,
          contentType: 'text/event-stream',
          body: eventStream(progress),
        },
        [`POST ${J}/cancel`]: { status: 200, body: { cancelled: true } },
      },
    },
    async ({ page, requests, setRoute }) => {
      await page.getByTestId('pdf-pages').waitFor()
      await page.getByRole('button', { name: 'Generează ciorna' }).click()
      const row = page.getByTestId('report-progress')
      await row.getByText('Capitolul 4 din 7 — Analiza consumurilor').waitFor()
      await row.getByText('3 / 7 capitole').waitFor()
      await page.getByRole('button', { name: 'Se scrie…' }).waitFor()
      const toc = page.getByTestId('report-toc')
      assert.equal(await toc.locator('[data-state="done"]').count(), 3)
      assert.equal(await toc.locator('[data-state="working"]').count(), 1)
      assert.deepEqual(requests.find((item) => item.path === `${J}/stages/audit_render`).body, {
        on_revision: 1,
      })
      await row.getByRole('button', { name: 'Opreşte' }).click()
      await settle(page)
      assert.equal(count(requests, 'POST', `${J}/cancel`), 1)
      const before = count(requests, 'GET', `${J}/audit/report`)
      setRoute(`GET ${J}/events`, {
        status: 200,
        contentType: 'text/event-stream',
        body: eventStream([
          ...progress,
          {
            run_id: 'run-draft-2',
            stage: 'audit_render',
            type: 'stage_finished',
            payload: { state: 'ready' },
          },
        ]),
      })
      await page.getByRole('button', { name: 'Generează ciorna' }).waitFor({ timeout: 15_000 })
      await settle(page)
      assert.ok(count(requests, 'GET', `${J}/audit/report`) > before)
    },
  )
})

test('the markers panel lists the empty fields and Le completez acum opens Revizuire', async () => {
  await withHarness({ path, routes: reportRoutes }, async ({ page }) => {
    const panel = page.getByTestId('report-panel')
    await panel.getByText('118 câmpuri confirmate').waitFor()
    await panel.getByText('2 câmpuri încă în revizuire').waitFor()
    await panel.getByText('9 tabele, 0 grafice').waitFor()
    await panel.getByText('formatate după şablonul EMA').waitFor()
    const markers = page.getByTestId('report-markers')
    await markers.getByText('3 câmpuri rămase goale').waitFor()
    await markers
      .getByText(
        'Concluziile privind analiza consumului · Măsuri de creştere a eficienţei energetice',
      )
      .waitFor()
    await panel.getByText('2 secţii · 4 tablouri măsurate · 3 măsuri').waitFor()
    await page.getByRole('button', { name: '3 câmpuri goale' }).click()
    assert.equal(await markers.evaluate((node) => node === document.activeElement), true)
    await panel.getByText('Audit-ciorna.docx').waitFor()
    await panel.getByText('Versiunea anterioară rămâne — nimic nu se suprascrie.').waitFor()
    // Revizuire is audit-work's screen with its own reads: record where the link goes, stay here.
    await page.evaluate(() => {
      const pushed = []
      window.__pushed = pushed
      history.pushState = (_state, _unused, url) => {
        pushed.push(String(url))
      }
    })
    await markers.getByRole('button', { name: 'Le completez acum' }).click()
    assert.deepEqual(await page.evaluate(() => window.__pushed), [`/app/audit/${JOB}/revizuire`])
  })
})

test('without Word the draft is offered for download instead of a preview', async () => {
  await withHarness(
    {
      path,
      routes: {
        ...reportRoutes,
        [`GET ${J}/audit/report`]: {
          status: 200,
          body: {
            ...REPORT,
            word: false,
            draft: {
              ...DRAFT_RUN,
              pdf_output_id: null,
              summary: { ...DRAFT_RUN.summary, pdf: false },
            },
          },
        },
        [`GET ${J}/outputs`]: { status: 200, body: OUTPUTS.slice(1) },
        [`GET ${J}/outputs/out-draft-docx`]: {
          status: 200,
          contentType: 'application/octet-stream',
          body: 'PK synthetic',
        },
      },
    },
    async ({ page, requests }) => {
      await page
        .getByText('Previzualizarea cere Microsoft Word. Ciorna se poate descărca.')
        .waitFor()
      const download = page.waitForEvent('download')
      await page.getByRole('button', { name: 'Descarcă ciorna' }).click()
      assert.equal((await download).suggestedFilename(), 'Audit-ciorna.docx')
      assert.equal(count(requests, 'GET', `${J}/outputs/out-draft-pdf`), 0)
    },
  )
})

test('an existing draft generates directly without an external-edit dialog', async () => {
  await withHarness(
    {
      path,
      routes: {
        ...reportRoutes,
        [`GET ${J}/outputs`]: {
          status: 200,
          body: OUTPUTS,
        },
        [`POST ${J}/stages/audit_render`]: started,
        [`GET ${J}/events`]: {
          status: 200,
          contentType: 'text/event-stream',
          body: eventStream(progress),
        },
      },
    },
    async ({ page, requests }) => {
      await page.getByTestId('pdf-pages').waitFor()
      await page.getByRole('button', { name: 'Generează ciorna' }).click()
      assert.equal(await page.getByRole('dialog').count(), 0)
      await page.getByTestId('report-progress').waitFor()
      assert.equal(count(requests, 'POST', `${J}/stages/audit_render`), 1)
    },
  )
})

test('a failed render names its cause; an unconfigured base says only that', async () => {
  const failed = { ...DRAFT_RUN, run_id: 'run-draft-9', state: 'failed', summary: null }
  await withHarness(
    {
      path,
      routes: {
        ...reportRoutes,
        [`GET ${J}/audit/report`]: { status: 200, body: { ...REPORT, draft: failed } },
        [`GET ${J}/events`]: {
          status: 200,
          contentType: 'text/event-stream',
          body: eventStream([
            {
              run_id: 'run-draft-9',
              stage: 'audit_render',
              type: 'stage_failed',
              payload: {
                code: 'audit_package',
                message: 'Pachetul Word al auditului este invalid.',
              },
            },
          ]),
        },
        [`POST ${J}/stages/audit_render`]: problem(
          'audit_base_missing',
          409,
          'Baza auditului nu este configurată.',
        ),
      },
    },
    async ({ page }) => {
      const notice = page.getByRole('alert').filter({ hasText: 'Raportul nu s-a generat' })
      await notice.getByText('Pachetul Word al auditului este invalid.').waitFor()
      await notice.getByRole('button', { name: 'Încearcă din nou' }).click()
      await page
        .getByRole('alert')
        .filter({ hasText: 'Baza auditului nu este configurată.' })
        .waitFor()
    },
  )
})

test('a preview that cannot load says so and can be retried', async () => {
  await withHarness(
    {
      path,
      routes: {
        ...reportRoutes,
        [`GET ${J}/outputs/out-draft-pdf`]: {
          status: 200,
          contentType: 'application/pdf',
          body: 'not a pdf',
        },
      },
    },
    async ({ page, requests, setRoute }) => {
      const notice = page
        .getByRole('alert')
        .filter({ hasText: 'Previzualizarea nu s-a putut încărca' })
      await notice.waitFor()
      setRoute(`GET ${J}/outputs/out-draft-pdf`, reportRoutes[`GET ${J}/outputs/out-draft-pdf`])
      await notice.getByRole('button', { name: 'Încearcă din nou' }).click()
      await page.getByTestId('pdf-pages').waitFor()
      assert.equal(count(requests, 'GET', `${J}/outputs/out-draft-pdf`), 2)
    },
  )
})
