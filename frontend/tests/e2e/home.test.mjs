import assert from 'node:assert/strict'
import test from 'node:test'
import { OVERVIEW } from '../fixtures/base.mjs'
import { problem } from './harness.mjs'
import { withHarness } from './helpers.mjs'

const settings = {
  theme: 'light',
  default_provider: null,
  providers: {
    gemini: { present: false, verified_at: null, hint: null, source: null },
    openai: { present: false, verified_at: null, hint: null, source: null },
  },
  extraction: { ocr: true, flag_uncertain: true, auto_accept_exact: false },
  workspace: '/synthetic/workspace',
  backup: { dir: '/synthetic/backups', last_at: null, last_size: null, last_name: null, due: true },
}

test('home orders in-progress jobs, links by type and shows one backup prompt', async () => {
  let current = structuredClone(settings)
  await withHarness(
    {
      routes: {
        'GET /settings': () => ({ body: current }),
        'POST /backups': () => {
          current = { ...current, backup: { ...current.backup, due: false } }
          return {
            status: 201,
            body: {
              name: 'ema-backup-synthetic.zip',
              path: '/synthetic/backups/ema-backup-synthetic.zip',
              created_at: '2026-09-27T12:00:00Z',
              size_bytes: 1024,
            },
          }
        },
      },
    },
    async ({ page, requests }) => {
      await page.getByRole('heading', { name: 'Bine ai revenit.' }).waitFor()
      const rows = page.locator('.home-job-row')
      // Jobs load after the heading renders; counting at once raced the fetch in CI.
      await rows.nth(2).waitFor()
      assert.equal(await rows.count(), 3)
      assert.match(await rows.first().innerText(), /Facturi 2026/)
      assert.equal(
        await rows.first().getByRole('link').getAttribute('href'),
        '/app/facturi/job-invoices-1',
      )
      assert.equal(
        await page.locator('.home-screen__section').innerText(),
        'UNDE AI RĂMAS\no lucrare aşteaptă o decizie de la tine',
      )
      assert.equal(await page.getByText('Un singur lucru, când ai timp').count(), 1)
      const refreshed = page.waitForResponse(
        (response) =>
          new URL(response.url()).pathname === '/settings' && current.backup.due === false,
      )
      await page.getByRole('button', { name: 'Fă copia acum' }).click()
      await refreshed
      await page.getByText('Copia e făcută: ema-backup-synthetic.zip').waitFor()
      assert.deepEqual(requests.find((item) => item.path === '/backups')?.body, {})
      assert.ok(requests.filter((item) => item.path === '/settings').length >= 2)
      assert.equal(await page.getByText('Copia e făcută: ema-backup-synthetic.zip').count(), 1)
    },
  )
})

test('missing backup folder offers settings; no due hides widget', async () => {
  await withHarness(
    {
      routes: {
        'GET /settings': { body: settings },
        'POST /backups': problem('backup_dir_missing', 409, 'Alege întâi dosarul pentru copii.'),
      },
    },
    async ({ page }) => {
      await page.getByRole('button', { name: 'Fă copia acum' }).click()
      await page.getByRole('button', { name: 'Alege dosarul' }).click()
      await page.waitForURL('**/app/setari/fisiere')
    },
  )
  await withHarness(
    {
      routes: {
        'GET /settings': { body: { ...settings, backup: { ...settings.backup, due: false } } },
      },
    },
    async ({ page }) => {
      await page.locator('.home-job-row').first().waitFor()
      assert.equal(await page.getByText('Un singur lucru, când ai timp').count(), 0)
    },
  )
})

test('home says all jobs are current when none blocks', async () => {
  const clear = OVERVIEW.map((job) => ({ ...job, blocking: 0 }))
  await withHarness(
    {
      routes: {
        'GET /jobs/overview': { body: clear },
        'GET /settings': { body: { ...settings, backup: { ...settings.backup, due: false } } },
      },
    },
    async ({ page }) => {
      await page.getByText('toate cele trei lucrări sunt la zi').waitFor()
    },
  )
})

test('home hides the attention sentence when every job is finished', async () => {
  await withHarness(
    {
      routes: {
        'GET /jobs/overview': { body: OVERVIEW.map((job) => ({ ...job, finalized: true })) },
        'GET /settings': { body: { ...settings, backup: { ...settings.backup, due: false } } },
      },
    },
    async ({ page }) => {
      await page.getByText('UNDE AI RĂMAS').waitFor()
      assert.equal(await page.locator('.home-screen__section span').count(), 1)
      assert.equal(await page.locator('.home-screen__section').innerText(), 'UNDE AI RĂMAS')
    },
  )
})

test('empty home opens an audit dialog and dark theme retains the screen', async () => {
  await withHarness(
    {
      theme: 'dark',
      routes: {
        'GET /jobs/overview': { body: [] },
        'GET /settings': { body: { ...settings, theme: 'dark' } },
      },
    },
    async ({ page }) => {
      await page.getByRole('heading', { name: 'Începe cu un audit' }).waitFor()
      await page
        .locator('.home-screen')
        .getByRole('button', { name: 'Lucrare nouă' })
        .last()
        .click()
      const dialog = page.getByRole('dialog', { name: 'Lucrare nouă' })
      assert.equal(await dialog.locator('input[type="radio"]:checked').count(), 1)
      assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), 'dark')
    },
  )
})
