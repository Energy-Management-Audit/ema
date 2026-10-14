import assert from 'node:assert/strict'
import test from 'node:test'
import { JOB } from '../fixtures/piee/default.mjs'
import { OVERVIEW } from '../fixtures/base.mjs'
import { problem } from './harness.mjs'
import { withHarness } from './helpers.mjs'

test('shell destinations, job link, finalized expansion and settings work', async () => {
  const finalized = [0, 1, 2].map((index) => ({
    ...OVERVIEW[0],
    id: `finished-${String(index)}`,
    year: 2023 + index,
    updated_at: `2026-09-27T08:0${String(index)}:00Z`,
    approved_at: `2026-09-27T08:0${String(index)}:00Z`,
    finalized: true,
  }))
  await withHarness(
    {
      path: '/app/clienti',
      routes: { 'GET /jobs/overview': { status: 200, body: [...OVERVIEW, ...finalized] } },
    },
    async ({ page }) => {
      await page.getByRole('heading', { name: 'Clienţi' }).waitFor()
      const sidebar = page.locator('.ema-sidebar')
      const finished = sidebar.locator('.ema-nav-group').last().locator('.ema-nav-job')
      await finished.first().waitFor()
      assert.equal(await finished.count(), 1)
      assert.match((await finished.first().textContent()) ?? '', /2025/)
      const reporting = sidebar.locator('.ema-nav-item__label', {
        hasText: 'Raportare manager energetic',
      })
      assert.equal(await reporting.getAttribute('title'), 'Raportare manager energetic')
      assert.deepEqual(
        await reporting.evaluate((element) => ({
          nowrap: getComputedStyle(element).whiteSpace === 'nowrap',
          ellipsis: getComputedStyle(element).textOverflow === 'ellipsis',
          clipped: element.scrollWidth > element.clientWidth,
        })),
        { nowrap: true, ellipsis: true, clipped: true },
      )
      await sidebar.getByRole('button', { name: 'încă două…' }).click()
      await finished.nth(2).waitFor()
      assert.equal(await sidebar.locator('.ema-nav-job').count(), 6)
      await sidebar.getByRole('button', { name: 'PIEE 2026' }).first().click()
      await page.waitForURL(`**/app/piee/${JOB}/date`)
      await sidebar.getByRole('button', { name: 'Raportare manager energetic' }).click()
      await page.waitForURL('**/app/raportare')
      await page.locator('.ema-sidebar').getByRole('button', { name: 'Setări' }).click()
      await page.waitForURL('**/app/setari')
      await page
        .locator('.ema-sidebar')
        .getByRole('button', { name: 'Înapoi la aplicaţie' })
        .click()
      await page.waitForURL('**/app/raportare')
    },
  )
})

test('new job posts the selected type, client and year, then opens its first step', async () => {
  const created = {
    id: 'new-invoice',
    type: 'invoices',
    client_slug: 'client-exemplu',
    year: 2026,
    state: 'created',
    revision: 1,
  }
  await withHarness(
    {
      path: '/app/clienti',
      routes: {
        'POST /jobs': { status: 200, body: { id: created.id } },
        [`GET /jobs/${created.id}`]: { status: 200, body: created },
      },
    },
    async ({ page, requests }) => {
      await page.getByRole('button', { name: 'Lucrare nouă' }).click()
      const dialog = page.getByRole('dialog', { name: 'Lucrare nouă' })
      const clientBox = await dialog.getByRole('combobox').boundingBox()
      const yearBox = await dialog.getByRole('textbox').boundingBox()
      assert.ok(clientBox && yearBox)
      assert.ok(Math.abs(clientBox.width - yearBox.width) <= 1)
      await dialog.getByText('Facturi', { exact: true }).click()
      await dialog.getByRole('combobox').fill('exemplu en')
      await dialog.getByRole('option', { name: /Exemplu Energie SA/ }).click()
      await dialog.getByRole('textbox').fill('2026')
      await dialog.getByRole('button', { name: 'Creează lucrarea' }).click()
      await page.waitForURL(`**/app/facturi/${created.id}`)
      assert.deepEqual(
        requests.find((item) => item.method === 'POST' && item.path === '/jobs')?.body,
        { type: 'invoices', client: 'client-exemplu', year: 2026 },
      )
    },
  )
})

test('new job leaves a problem in the dialog and adds a client typed by name when none exist', async () => {
  await withHarness(
    {
      path: '/app/clienti',
      routes: { 'POST /jobs': problem('client_missing', 404, 'Clientul lipseşte.') },
    },
    async ({ page }) => {
      await page.getByRole('button', { name: 'Lucrare nouă' }).click()
      const dialog = page.getByRole('dialog')
      await dialog.getByText('PIEE', { exact: true }).click()
      await dialog.getByRole('combobox').fill('exemplu en')
      await dialog.getByRole('option', { name: /Exemplu Energie SA/ }).click()
      await dialog.getByRole('button', { name: 'Creează lucrarea' }).click()
      await dialog.getByRole('alert').getByText('Clientul lipseşte.').first().waitFor()
    },
  )
  await withHarness(
    {
      path: '/app/clienti',
      routes: {
        'GET /clients': { status: 200, body: [] },
        'POST /clients': {
          status: 201,
          body: { id: 'client-new', name: 'Client nou', cui: null, revision: 1 },
        },
        'POST /jobs': { status: 200, body: { id: 'new-invoice' } },
        'GET /jobs/new-invoice': {
          status: 200,
          body: {
            id: 'new-invoice',
            type: 'invoices',
            client_slug: 'client-new',
            year: 2026,
            state: 'created',
            revision: 1,
          },
        },
      },
    },
    async ({ page, requests }) => {
      await page.getByRole('button', { name: 'Lucrare nouă' }).click()
      const dialog = page.getByRole('dialog')
      assert.equal(await dialog.getByText('Adaugă întâi clientul.').count(), 0)
      await dialog.getByText('Facturi', { exact: true }).click()
      await dialog.getByRole('combobox').fill('Client nou')
      await dialog.getByRole('option', { name: 'Adaugă clientul „Client nou”' }).click()
      await dialog.getByRole('textbox').fill('2026')
      await dialog.getByRole('button', { name: 'Creează lucrarea' }).click()
      await page.waitForURL('**/app/facturi/new-invoice')
      assert.deepEqual(
        requests.find((item) => item.method === 'POST' && item.path === '/clients')?.body,
        { name: 'Client nou', cui: null },
      )
      assert.deepEqual(
        requests.find((item) => item.method === 'POST' && item.path === '/jobs')?.body,
        { type: 'invoices', client: 'client-new', year: 2026 },
      )
    },
  )
})

test('a PIEE job opened with the audit prefix redirects to its own route', async () => {
  await withHarness({ path: `/app/audit/${JOB}/masuratori` }, async ({ page }) => {
    await page.waitForURL(`**/app/piee/${JOB}/date`)
  })
})

test('the dialog resets on reopen and a failed overview can be retried', async () => {
  await withHarness(
    {
      path: '/app/clienti',
      routes: { 'GET /jobs/overview': problem('request_error', 500, 'Citirea a eşuat.') },
    },
    async ({ page, setRoute }) => {
      await page.getByRole('alert').getByText('Nu am putut încărca lucrările').waitFor()
      setRoute('GET /jobs/overview', { status: 200, body: OVERVIEW })
      await page.getByRole('button', { name: 'Încearcă din nou' }).click()
      await page.locator('.ema-sidebar').getByRole('button', { name: 'PIEE 2026' }).waitFor()
      await page.getByRole('button', { name: 'Lucrare nouă' }).click()
      let dialog = page.getByRole('dialog')
      await dialog.getByText('Facturi', { exact: true }).click()
      await dialog.getByRole('button', { name: 'Renunţă' }).click()
      await page.getByRole('button', { name: 'Lucrare nouă' }).click()
      dialog = page.getByRole('dialog')
      assert.equal(await dialog.locator('input[type="radio"]:checked').count(), 0)
    },
  )
})
