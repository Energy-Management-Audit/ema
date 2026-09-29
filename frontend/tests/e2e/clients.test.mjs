import assert from 'node:assert/strict'
import test from 'node:test'
import { CLIENT_ROUTES, PROFILE } from '../fixtures/clients/default.mjs'
import { OVERVIEW } from '../fixtures/base.mjs'
import { problem } from './harness.mjs'
import { withHarness } from './helpers.mjs'

const year = new Date().getFullYear() - 1

test('M1 counts, filters, search and row navigation', async () => {
  await withHarness({ path: '/app/clienti', routes: CLIENT_ROUTES }, async ({ page }) => {
    await page.getByRole('heading', { name: 'Clienţi' }).waitFor()
    await page.getByText(`10 clienţi · 4 cu Anexa 2–3 pentru ${String(year)}`).waitFor()
    assert.equal(await page.locator('.clients-table__row').count(), 10)
    await page.getByRole('tab', { name: `Fără anexă ${String(year)} 6` }).click()
    assert.equal(await page.locator('.clients-table__row').count(), 6)
    await page.getByRole('tab', { name: 'Date ANAF vechi 9' }).click()
    assert.equal(await page.locator('.clients-table__row').count(), 9)
    await page.getByRole('tab', { name: 'Cu lucrări în curs 2' }).click()
    assert.equal(await page.locator('.clients-table__row').count(), 2)
    await page.getByRole('tab', { name: 'Toţi 10' }).click()
    const search = page.getByRole('textbox', { name: 'Caută clienţi' })
    await search.fill('exemplu energie')
    assert.equal(await page.locator('.clients-table__row').count(), 1)
    await search.fill('1234567')
    assert.equal(await page.locator('.clients-table__row').count(), 1)
    await search.fill('RO001234567890123456')
    assert.equal(await page.locator('.clients-table__row').count(), 1)
    await page.locator('.clients-table__row').click()
    await page.waitForURL('**/app/clienti/client-exemplu/date')
  })
})

test('new client lookup handles existing and unavailable ANAF', async () => {
  await withHarness(
    {
      path: '/app/clienti',
      routes: {
        ...CLIENT_ROUTES,
        'POST /clients/from-anaf': problem('client_exists', 409, 'Clientul există deja.'),
      },
    },
    async ({ page, requests, setRoute }) => {
      await page.getByRole('button', { name: 'Client nou după CUI' }).click()
      let dialog = page.getByRole('dialog', { name: 'Client nou' })
      await dialog.getByRole('textbox', { name: 'CUI' }).fill('RO 1234567')
      await dialog.getByRole('button', { name: 'Caută în ANAF' }).click()
      await dialog.getByRole('button', { name: 'Deschide clientul' }).click()
      await page.waitForURL('**/app/clienti/client-exemplu/date')
      assert.deepEqual(requests.find((item) => item.path === '/clients/from-anaf')?.body, {
        cui: 'RO 1234567',
      })
      await page
        .locator('.ema-sidebar')
        .getByRole('button', { name: /Clienţi/ })
        .click()
      setRoute(
        'POST /clients/from-anaf',
        problem('anaf_unavailable', 424, 'Registrul ANAF nu este disponibil.'),
      )
      setRoute('POST /clients', {
        status: 201,
        body: { ...PROFILE.client, id: 'client-new', name: 'Client nou' },
      })
      setRoute('GET /clients/client-new/profile', {
        status: 200,
        body: { ...PROFILE, client: { ...PROFILE.client, id: 'client-new', name: 'Client nou' } },
      })
      await page.getByRole('button', { name: 'Client nou după CUI' }).click()
      dialog = page.getByRole('dialog', { name: 'Client nou' })
      await dialog.getByRole('textbox', { name: 'CUI' }).fill('RO 98765432')
      await dialog.getByRole('button', { name: 'Caută în ANAF' }).click()
      await dialog.getByRole('textbox', { name: 'Denumire' }).fill('Client nou')
      await dialog.getByRole('button', { name: 'Adaugă fără ANAF' }).click()
      await page.waitForURL('**/app/clienti/client-new/date')
      assert.deepEqual(
        requests.find((item) => item.path === '/clients' && item.method === 'POST')?.body,
        { name: 'Client nou', cui: '98765432' },
      )
    },
  )
})

test('new client uses ANAF identity when the lookup succeeds', async () => {
  await withHarness(
    {
      path: '/app/clienti',
      routes: {
        ...CLIENT_ROUTES,
        'POST /clients/from-anaf': {
          status: 201,
          body: { ...PROFILE.client, id: 'client-anaf-new' },
        },
        'GET /clients/client-anaf-new/profile': {
          status: 200,
          body: { ...PROFILE, client: { ...PROFILE.client, id: 'client-anaf-new' } },
        },
      },
    },
    async ({ page, requests }) => {
      await page.getByRole('button', { name: 'Client nou după CUI' }).click()
      const dialog = page.getByRole('dialog', { name: 'Client nou' })
      await dialog.getByRole('textbox', { name: 'CUI' }).fill('RO 22334455')
      await dialog.getByRole('button', { name: 'Caută în ANAF' }).click()
      await page.waitForURL('**/app/clienti/client-anaf-new/date')
      await page.getByText('IDENTIFICARE · DIN ANAF').waitFor()
      await page.getByText('manager energetic', { exact: true }).waitFor()
      assert.deepEqual(requests.find((item) => item.path === '/clients/from-anaf')?.body, {
        cui: 'RO 22334455',
      })
    },
  )
})

test('M2 keeps raw annex CUI visible and refetches a stale contact revision', async () => {
  let reads = 0
  const annexProfile = {
    ...PROFILE,
    identification: {
      ...PROFILE.identification,
      source: 'annex',
      cui: 'CUI: 1234567 / 87654321',
      annex_year: year,
      retrieved_at: null,
    },
    fiscal: null,
  }
  await withHarness(
    {
      path: '/app/clienti/client-exemplu/date',
      routes: {
        ...CLIENT_ROUTES,
        'GET /clients/client-exemplu/profile': () => {
          reads += 1
          return {
            status: 200,
            body: {
              ...annexProfile,
              client: { ...annexProfile.client, revision: reads === 1 ? 1 : 2 },
            },
          }
        },
        'PATCH /clients/client-exemplu': problem(
          'stale_revision',
          409,
          'Clientul a fost modificat între timp.',
        ),
      },
    },
    async ({ page }) => {
      await page.getByText(`IDENTIFICARE · DIN ANEXA 2–3 ${String(year)}`).waitFor()
      await page.getByText('CUI: 1234567 / 87654321').waitFor()
      await page.getByRole('button', { name: 'Completează' }).click()
      await page.getByRole('textbox', { name: 'Nume contact' }).fill('Contact nou')
      await page.getByRole('button', { name: 'Salvează' }).click()
      await page.getByText('Clientul a fost modificat între timp.').first().waitFor()
      await page.waitForFunction(() =>
        document
          .querySelector('.client-screen')
          ?.textContent?.includes('Clientul a fost modificat între timp.'),
      )
      assert.ok(reads >= 2)
    },
  )
})

test('M2 removes one site with the current client revision', async () => {
  const site = { id: 'site-1', name: 'Punct Exemplu', address: 'Strada Test 1' }
  await withHarness(
    {
      path: '/app/clienti/client-exemplu/puncte',
      routes: {
        ...CLIENT_ROUTES,
        'GET /clients/client-exemplu/profile': {
          status: 200,
          body: { ...PROFILE, client: { ...PROFILE.client, sites: [site] } },
        },
        'PATCH /clients/client-exemplu': { status: 200, body: PROFILE.client },
      },
    },
    async ({ page, requests }) => {
      await page.getByText('Punct Exemplu').waitFor()
      await page.getByRole('button', { name: 'Scoate' }).click()
      assert.deepEqual(
        requests.find((item) => item.method === 'PATCH' && item.path === '/clients/client-exemplu')
          ?.body,
        {
          sites: [],
          on_revision: 1,
        },
      )
    },
  )
})

test('M2 uses the full job label in rows and the destructive title', async () => {
  await withHarness(
    {
      path: '/app/clienti/client-doi/lucrari',
      routes: {
        ...CLIENT_ROUTES,
        'GET /clients/client-doi/profile': {
          status: 200,
          body: {
            ...PROFILE,
            client: { ...PROFILE.client, id: 'client-doi', name: 'Doi Industrie SRL' },
          },
        },
        'GET /jobs/job-audit-1/slots': { status: 200, body: [] },
        'GET /jobs/job-audit-1/fields': { status: 200, body: [] },
      },
    },
    async ({ page }) => {
      const row = page.locator('.client-list__row', { hasText: 'Audit energetic 2026' })
      await row.waitFor()
      await row.getByRole('button', { name: 'Şterge' }).click()
      await page
        .getByRole('dialog', { name: 'Ştergi „Audit energetic 2026 · Doi Industrie SRL”?' })
        .waitFor()
    },
  )
})

test('M2 contact, sites, memory, jobs and 7c delete use revision-safe calls', async () => {
  let jobs = OVERVIEW
  await withHarness(
    {
      path: '/app/clienti/client-exemplu/date',
      routes: {
        ...CLIENT_ROUTES,
        'GET /jobs/overview': () => ({ status: 200, body: jobs }),
        'PATCH /clients/client-exemplu': { status: 200, body: PROFILE.client },
        'DELETE /jobs/job-piee-1': () => {
          jobs = jobs.filter((job) => job.id !== 'job-piee-1')
          return { status: 200, body: { deleted: true } }
        },
      },
    },
    async ({ page, requests }) => {
      await page.getByText('IDENTIFICARE · DIN ANAF').waitFor()
      await page.getByText('activ · plătitor TVA').waitFor()
      await page.getByText('Nu apare în Anexa 2–3').waitFor()
      await page.getByRole('button', { name: 'Completează' }).click()
      await page.getByRole('textbox', { name: 'Nume contact' }).fill('Contact nou')
      await page.getByRole('button', { name: 'Salvează' }).click()
      const contactPatch = requests.find(
        (item) => item.method === 'PATCH' && item.path === '/clients/client-exemplu',
      )
      assert.equal(contactPatch?.body.on_revision, 1)
      assert.equal(contactPatch?.body.contacts.at(-1).role, 'contact')
      await page.getByRole('tab', { name: /Puncte de lucru/ }).click()
      await page.getByRole('button', { name: 'Adaugă punct de lucru' }).click()
      await page.getByRole('textbox', { name: 'Denumire' }).fill('Punct nou')
      await page.getByRole('textbox', { name: 'Adresă' }).fill('Strada Test 1')
      await page.getByRole('button', { name: 'Salvează' }).click()
      assert.ok(
        requests.some(
          (item) => item.method === 'PATCH' && item.body?.sites?.at(-1)?.name === 'Punct nou',
        ),
      )
      await page.getByRole('tab', { name: /Memorie CUI\/POD/ }).click()
      await page.getByText('retras').waitFor()
      await page.getByRole('tab', { name: /Lucrări/ }).click()
      await page
        .locator('.client-list__row', { hasText: 'PIEE 2026' })
        .getByRole('button', { name: 'Şterge' })
        .click()
      const dialog = page.getByRole('dialog', { name: /Ştergi/ })
      await dialog.getByText(/Se şterg 3 fişiere/).waitFor()
      await dialog.getByRole('button', { name: 'Şterge lucrarea' }).click()
      await page
        .locator('.client-list__row', { hasText: 'PIEE 2026' })
        .waitFor({ state: 'detached' })
      assert.deepEqual(
        requests.find((item) => item.method === 'DELETE' && item.path === '/jobs/job-piee-1')?.body,
        { confirm: true, on_revision: 7 },
      )
    },
  )
})

test('F20 client search has a visible focus ring in both themes', async () => {
  for (const theme of ['light', 'dark']) {
    await withHarness({ path: '/app/clienti', routes: CLIENT_ROUTES, theme }, async ({ page }) => {
      const search = page.getByRole('textbox', { name: 'Caută clienţi' })
      await search.focus()
      assert.notEqual(
        await search.evaluate((node) => getComputedStyle(node.parentElement).boxShadow),
        'none',
      )
      assert.equal(await page.title(), 'Ema — Clienţi')
      await page
        .locator('.ema-sidebar')
        .getByRole('button', { name: 'Raportare manager energetic' })
        .click()
      await page.waitForURL('**/app/raportare')
      await page.waitForFunction(() => document.title === 'Ema — Raportare manager energetic')
    })
  }
})
