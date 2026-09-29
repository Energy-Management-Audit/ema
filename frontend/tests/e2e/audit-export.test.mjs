// 7a Predare for an audit on the synthetic fixture (D7, D10 frontend).

import assert from 'node:assert/strict'
import test from 'node:test'
import {
  DRAFT_RUN,
  FINAL_OUTPUTS,
  FINAL_RUN,
  J,
  JOB,
  ANSWERED,
  READY_CHECKS,
  REPORT,
  eventStream,
  reportRoutes,
} from '../fixtures/audit-report/default.mjs'
import { problem } from './harness.mjs'
import { count, settle, withHarness } from './helpers.mjs'

const path = `/app/audit/${JOB}/predare`
const withFinal = {
  ...reportRoutes,
  [`GET ${J}/outputs`]: { status: 200, body: FINAL_OUTPUTS },
  [`GET ${J}/export/checks`]: { status: 200, body: READY_CHECKS },
  [`GET ${J}/sections`]: { status: 200, body: ANSWERED },
  [`GET ${J}/audit/report`]: { status: 200, body: { ...REPORT, final: FINAL_RUN } },
}

async function checkRows(page) {
  const rows = page.locator('[data-testid^="export-check-"]')
  await rows.first().waitFor()
  return rows.evaluateAll((nodes) =>
    nodes.map((node) => [
      node.querySelector('.ema-export-check__label').textContent,
      node.dataset.tone,
      node.querySelector('.ema-export-check__detail').textContent,
    ]),
  )
}

test('the five checks come from the blocking codes; the photo check hides without photos', async () => {
  await withHarness({ path, routes: reportRoutes }, async ({ page }) => {
    assert.deepEqual(await checkRows(page), [
      ['Toate secţiunile au răspuns', 'err', '2/4'],
      ['Nicio ciornă nu e veche', 'ok', 'la zi'],
      ['Toate diferenţele dintre surse sunt decise', 'err', '1'],
      ['Valorile citite de pe fotografii sunt confirmate', 'err', '1'],
      ['Toate textele sunt scrise', 'err', '1'],
    ])
    await page
      .getByText('Raportul nu e încă gata de predare. Rezolvă ce e marcat mai jos.')
      .waitFor()
    await page.getByText('Audit-ciorna.docx').waitFor()
    await page.getByText('Audit-ciorna.pdf').waitFor()
    await page.getByText('6 CAPITOLE · 3 PAGINI').waitFor()
  })
  await withHarness(
    {
      path,
      routes: {
        ...reportRoutes,
        [`GET ${J}/visit`]: { status: 200, body: { panels: [], thermal: [] } },
      },
    },
    async ({ page }) => {
      const labels = (await checkRows(page)).map((row) => row[0])
      assert.equal(labels.length, 4)
      assert.ok(!labels.includes('Valorile citite de pe fotografii sunt confirmate'))
    },
  )
})

test('X1: the final waits for final_ok, then starts audit_final', async () => {
  await withHarness({ path, routes: reportRoutes }, async ({ page }) => {
    const button = page.getByRole('button', { name: 'Generează versiunea finală' })
    await button.waitFor()
    assert.equal(await button.isDisabled(), true)
    await page.getByText('Date generale: Completați şi confirmați').waitFor()
    await page.getByRole('button', { name: 'Descarcă ciorna' }).waitFor()
  })
  await withHarness(
    {
      path,
      routes: {
        ...reportRoutes,
        [`GET ${J}/export/checks`]: { status: 200, body: READY_CHECKS },
        [`POST ${J}/stages/audit_final`]: {
          status: 202,
          body: { run_id: 'run-final-2', stage: 'audit_final', state: 'running' },
        },
      },
    },
    async ({ page, requests }) => {
      await page.getByText('Raportul e complet pentru predare.', { exact: false }).waitFor()
      await page.getByRole('button', { name: 'Generează versiunea finală' }).click()
      await settle(page)
      assert.deepEqual(requests.find((item) => item.path === `${J}/stages/audit_final`).body, {
        on_revision: 1,
      })
    },
  )
})

test('X3: approving posts exactly the listed final and the readiness shown', async () => {
  await withHarness(
    {
      path,
      routes: {
        ...withFinal,
        [`POST ${J}/export`]: { status: 200, body: { output_id: 'out-final-docx' } },
      },
    },
    async ({ page, requests, setRoute }) => {
      await page.getByText('Audit-final.docx').waitFor()
      await page.getByText('6 CAPITOLE · 4 PAGINI').waitFor()
      await settle(page)
      const before = requests.length
      setRoute(`GET ${J}/approvals`, {
        status: 200,
        body: [
          {
            id: 'appr-1',
            job_id: JOB,
            output_id: 'out-final-docx',
            readiness_hash: 'hash-ready',
            on_decision: null,
            at: new Date().toISOString(),
            actor: 'user',
          },
        ],
      })
      await page.getByRole('button', { name: 'Aprobă şi exportă' }).click()
      await page.getByText('Copia finală e în dosarul de exporturi al lucrării.').waitFor()
      const after = requests.slice(before)
      assert.equal(after[0].method, 'POST')
      assert.equal(after[0].path, `${J}/export`)
      assert.deepEqual(after[0].body, {
        final: true,
        output_id: 'out-final-docx',
        readiness_hash: 'hash-ready',
        confirm: true,
      })
      await page.getByText(/^Aprobat acum/).waitFor()
      assert.equal(await page.getByRole('button', { name: 'Aprobă şi exportă' }).count(), 0)
    },
  )
})

test('X4 after a reload, and a hash mismatch refetches instead of retrying', async () => {
  await withHarness(
    {
      path,
      routes: {
        ...withFinal,
        [`GET ${J}/approvals`]: {
          status: 200,
          body: [
            {
              id: 'appr-1',
              job_id: JOB,
              output_id: 'out-final-docx',
              readiness_hash: 'hash-ready',
              on_decision: null,
              at: '2026-09-27T08:00:00+00:00',
              actor: 'user',
            },
          ],
        },
      },
    },
    async ({ page }) => {
      await page.getByText(/^Aprobat /).waitFor()
      assert.equal(await page.getByRole('button', { name: 'Aprobă şi exportă' }).count(), 0)
      assert.equal(
        await page.getByText('Copia finală e în dosarul de exporturi al lucrării.').count(),
        0,
      )
    },
  )
  await withHarness(
    {
      path,
      routes: {
        ...withFinal,
        [`POST ${J}/export`]: problem(
          'hash_mismatch',
          403,
          'Versiunea de pregătire nu corespunde.',
        ),
      },
    },
    async ({ page, requests }) => {
      await page.getByText('Audit-final.docx').waitFor()
      const reads = count(requests, 'GET', `${J}/export/checks`)
      await page.getByRole('button', { name: 'Aprobă şi exportă' }).click()
      await page
        .getByText('Datele s-au schimbat de când ai deschis pagina. Verifică din nou.')
        .waitFor()
      await settle(page)
      assert.equal(count(requests, 'POST', `${J}/export`), 1)
      assert.ok(count(requests, 'GET', `${J}/export/checks`) > reads)
    },
  )
})

test('a final refused for markers says so by its title', async () => {
  const failed = { ...FINAL_RUN, run_id: 'run-final-9', state: 'failed', current: false }
  await withHarness(
    {
      path,
      routes: {
        ...reportRoutes,
        [`GET ${J}/export/checks`]: { status: 200, body: READY_CHECKS },
        [`GET ${J}/audit/report`]: {
          status: 200,
          body: { ...REPORT, draft: DRAFT_RUN, final: failed },
        },
        [`GET ${J}/status`]: {
          status: 200,
          body: {
            id: JOB,
            type: 'audit',
            state: 'open',
            revision: 1,
            runs: [
              {
                id: 'run-final-9',
                stage: 'audit_final',
                state: 'failed',
                error: 'Etapa a eşuat.',
              },
            ],
          },
        },
        [`GET ${J}/events`]: {
          status: 200,
          contentType: 'text/event-stream',
          body: eventStream([
            {
              run_id: 'run-final-9',
              stage: 'audit_final',
              type: 'stage_failed',
              payload: {
                code: 'audit_markers',
                message: 'Raportul final are câmpuri necompletate.',
              },
            },
          ]),
        },
      },
    },
    async ({ page }) => {
      const notice = page
        .getByRole('alert')
        .filter({ hasText: 'Raportul final are câmpuri necompletate.' })
      await notice.waitFor()
      // The API masks a run's stored error; the title is the refusal's own message.
      assert.equal(await notice.getByText('Etapa a eşuat.').count(), 0)
    },
  )
})

test('a final refused before it starts shows the problem title', async () => {
  await withHarness(
    {
      path,
      routes: {
        ...reportRoutes,
        [`GET ${J}/export/checks`]: { status: 200, body: READY_CHECKS },
        [`POST ${J}/stages/audit_final`]: problem(
          'word_unavailable',
          424,
          'Microsoft Word nu este disponibil.',
        ),
      },
    },
    async ({ page }) => {
      await page.getByRole('button', { name: 'Generează versiunea finală' }).click()
      await page
        .getByRole('alert')
        .filter({ hasText: 'Microsoft Word nu este disponibil.' })
        .waitFor()
    },
  )
})

test('over a stale final X1 offers the new final even though the old one blocks export', async () => {
  const stale = {
    readiness: {
      draft_ok: true,
      final_ok: false,
      blocking: [
        {
          code: 'final_stale',
          field_id: null,
          message: 'Versiunea finală nu mai corespunde datelor. Generează-o din nou.',
        },
      ],
      warnings: [],
      next: [],
    },
    readiness_hash: 'hash-stale',
  }
  await withHarness(
    {
      path,
      routes: {
        ...reportRoutes,
        [`GET ${J}/outputs`]: { status: 200, body: FINAL_OUTPUTS },
        [`GET ${J}/export/checks`]: { status: 200, body: stale },
        [`GET ${J}/sections`]: { status: 200, body: ANSWERED },
        [`GET ${J}/audit/report`]: {
          status: 200,
          body: { ...REPORT, final: { ...FINAL_RUN, current: false } },
        },
      },
    },
    async ({ page }) => {
      // Wait for every read (checks, report, outputs) before looking at the button.
      await page
        .getByText('Versiunea finală nu mai corespunde datelor. Generează-o din nou.')
        .waitFor()
      await page.getByText('Audit-ciorna.docx').waitFor()
      const button = page.getByRole('button', { name: 'Generează versiunea finală' })
      await page.waitForFunction(() =>
        [...document.querySelectorAll('button')].some(
          (node) => node.textContent === 'Generează versiunea finală' && !node.disabled,
        ),
      )
      assert.equal(await button.isDisabled(), false)
      assert.equal(await page.getByRole('button', { name: 'Aprobă şi exportă' }).count(), 0)
      const rows = page.locator('[data-testid="export-check-2"]')
      assert.equal(await rows.getAttribute('data-tone'), 'err')
    },
  )
})

test('an empty chapter is visible in the existing sections check and blocks the final', async () => {
  const message = 'DESCRIEREA ŞI ISTORICUL SOCIETĂŢII: capitolul nu are conținut'
  await withHarness(
    {
      path,
      routes: {
        ...reportRoutes,
        [`GET ${J}/export/checks`]: {
          status: 200,
          body: {
            ...READY_CHECKS,
            readiness: {
              draft_ok: true,
              final_ok: false,
              blocking: [{ code: 'chapter_empty', message }],
            },
          },
        },
      },
    },
    async ({ page }) => {
      assert.equal((await checkRows(page))[0][1], 'err')
      await page.getByText(message, { exact: true }).waitFor()
      assert.equal(
        await page.getByRole('button', { name: 'Generează versiunea finală' }).isDisabled(),
        true,
      )
    },
  )
})
