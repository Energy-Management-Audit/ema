// The builder's D11 behaviour tests on the synthetic fixture.

import assert from 'node:assert/strict'
import test from 'node:test'
import { ANNUAL, CHECKS, FIELDS, JOB, REGISTRU, eventStream } from '../fixtures/piee/default.mjs'
import { problem } from './harness.mjs'
import { count, settle, withHarness } from './helpers.mjs'

const J = `/jobs/${JOB}`

test('B1 B2 boot: session, csrf, fragment dropped, theme, lands on S3', async () => {
  const decided = {
    status: 200,
    body: {
      id: 'd-9',
      at: '2026-09-25T09:00:00Z',
      actor: 'user',
      field_id: 'f-registru',
      on_revision: 1,
      action: 'correct',
      before: {},
      after: {},
    },
  }
  await withHarness(
    { theme: 'dark', routes: { [`POST ${J}/fields/f-registru/decide`]: decided } },
    async ({ page, requests }) => {
      await page.waitForURL(`**/app/piee/${JOB}/date`)
      const session = requests.find((item) => item.path === '/session')
      assert.deepEqual(session.body, { code: 'test-code' })
      assert.equal(await page.evaluate(() => localStorage.getItem('ema.csrf')), 'csrf-token')
      assert.equal(await page.evaluate(() => location.hash), '')
      assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), 'dark')
      await page.getByTestId('carrier-table-electricity_grid').waitFor()
      await page.getByRole('button', { name: 'Scrie valoarea' }).click()
      await page.getByLabel('Nr. Registrul Comerţului').fill('J00/000/2000')
      await page.getByRole('button', { name: 'Salvează' }).click()
      await settle(page)
      const mutations = requests.filter((item) => item.method !== 'GET')
      assert.ok(mutations.length >= 2)
      for (const item of mutations) assert.ok('x-ema-csrf' in item.headers, item.path)
      assert.equal(mutations.at(-1).headers['x-ema-csrf'], 'csrf-token')
    },
  )
})

test('B3 a deep link reloads S4 without a new session', async () => {
  await withHarness({ path: `/app/piee/${JOB}/masuri` }, async ({ page, requests }) => {
    await page.getByTestId('annual-check').waitFor()
    await page.evaluate(() => {
      history.replaceState(null, '', location.pathname)
    })
    const before = count(requests, 'POST', '/session')
    await page.reload()
    await page.getByTestId('measure-row-measure.planned.1').waitFor()
    assert.equal(count(requests, 'POST', '/session'), before)
    assert.ok(page.url().endsWith(`/app/piee/${JOB}/masuri`))
  })
})

test('B4 sidebar, tabs, and a tab switch refetches the job and its checks', async () => {
  await withHarness({}, async ({ page, requests }) => {
    await page.getByTestId('carrier-table-electricity_grid').waitFor()
    const nav = page.locator('.ema-sidebar')
    assert.match(await nav.innerText(), /ÎN LUCRU/)
    assert.match(await nav.innerText(), /Exemplu Energie SA/)
    const job = page.locator('.ema-nav-job[aria-current="page"]')
    assert.equal((await job.innerText()).replace(/\s+/g, ' ').trim(), 'PIEE 2026 1')
    const tabs = await page.getByRole('tab').allInnerTexts()
    assert.deepEqual(
      tabs.map((text) => text.replace(/\s+/g, ' ').trim()),
      ['Documente 3', 'Date 2023–2025', 'Măsuri 7', 'Jurnal'],
    )
    const jobs = count(requests, 'GET', J)
    const checks = count(requests, 'GET', `${J}/export/checks`)
    await page.getByRole('tab', { name: /Măsuri/ }).click()
    await page.waitForURL(`**/app/piee/${JOB}/masuri`)
    await settle(page)
    assert.ok(count(requests, 'GET', J) > jobs)
    assert.ok(count(requests, 'GET', `${J}/export/checks`) > checks)
  })
})

test('B5 B6 the carrier tables', async () => {
  await withHarness({}, async ({ page }) => {
    const grid = page.getByTestId('carrier-table-electricity_grid')
    await grid.waitFor()
    assert.match(await grid.innerText(), /Energie electrică din SEN · MWh/i)
    assert.equal(await grid.locator('tbody tr').count(), 3)
    assert.match(await grid.innerText(), /2 811,40/)
    await grid.getByRole('button', { name: 'Arată toate lunile' }).click()
    assert.equal(
      await grid.getByRole('button', { name: 'Arată toate lunile' }).getAttribute('aria-expanded'),
      'true',
    )
    const heads = await grid.locator('thead th').allInnerTexts()
    for (const month of ['IAN', 'MAI', 'IUN', 'IUL', 'AUG', 'SEP', 'OCT', 'NOI', 'DEC']) {
      assert.ok(heads.map((item) => item.toUpperCase()).includes(month), month)
    }
    const pv = page.getByTestId('carrier-table-electricity_pv')
    assert.match(
      (await pv.innerText()).replace(/\s+/g, ' '),
      /date lunare indisponibile · doar totalul anual, 61,32 MWh/,
    )
  })
})

test('B7 the banner leads to the conflict; choosing posts the candidate and refetches', async () => {
  await withHarness({}, async ({ page, requests, setRoute }) => {
    await page.getByText('Totalul anual nu se potriveşte cu Anexa 2–3').waitFor()
    await page.getByRole('link', { name: 'Du-mă la conflict' }).click()
    await page.waitForURL('**?camp=f-annual')
    const row = page.getByTestId('conflict-row-f-annual')
    await row.getByRole('button', { name: 'Foloseşte 22 161,92' }).waitFor()
    const decided = {
      ...ANNUAL,
      value: '22161.92',
      chosen: 'c-anexa',
      confidence: 'exact',
      review: 'accepted',
      revision: 4,
    }
    setRoute(`POST ${J}/conflicts/f-annual`, {
      status: 200,
      body: {
        id: 'd-9',
        at: '2026-09-25T09:00:00Z',
        actor: 'user',
        field_id: 'f-annual',
        on_revision: 3,
        action: 'choose',
        before: ANNUAL,
        after: decided,
      },
    })
    const counts = ['fields', 'export/checks', 'piee/summary', 'log'].map((path) =>
      count(requests, 'GET', `${J}/${path}`),
    )
    setRoute(`GET ${J}/fields`, {
      status: 200,
      body: FIELDS.map((item) => (item.id === 'f-annual' ? decided : item)),
    })
    await row.getByRole('button', { name: 'Foloseşte 22 161,92' }).click()
    await page.getByTestId('conflict-row-f-annual').waitFor({ state: 'detached' })
    const post = requests.find(
      (item) => item.method === 'POST' && item.path === `${J}/conflicts/f-annual`,
    )
    assert.deepEqual(post.body, { candidate_id: 'c-anexa', on_revision: 3 })
    const after = ['fields', 'export/checks', 'piee/summary', 'log'].map((path) =>
      count(requests, 'GET', `${J}/${path}`),
    )
    after.forEach((value, index) => {
      assert.ok(value > counts[index])
    })
  })
})

test('B8 a stale revision shows the problem, refetches the fields, never retries', async () => {
  await withHarness(
    {
      path: `/app/piee/${JOB}/date?camp=f-annual`,
      routes: {
        [`POST ${J}/conflicts/f-annual`]: problem(
          'stale_revision',
          409,
          'Câmpul a fost modificat între timp.',
        ),
      },
    },
    async ({ page, requests }) => {
      const row = page.getByTestId('conflict-row-f-annual')
      const fieldsBefore = () => count(requests, 'GET', `${J}/fields`)
      await row.getByRole('button', { name: 'Foloseşte 22 161,92' }).click()
      await page.getByText('Câmpul a fost modificat între timp.').waitFor()
      const before = fieldsBefore()
      await settle(page)
      assert.ok(before >= 2)
      assert.equal(count(requests, 'POST', `${J}/conflicts/f-annual`), 1)
    },
  )
})

test('B9 writing values: text, a Romanian number, a bad number', async () => {
  await withHarness(
    { path: `/app/piee/${JOB}/date?camp=f-annual` },
    async ({ page, requests, setRoute }) => {
      const reply = {
        status: 200,
        body: {
          id: 'd-10',
          at: '2026-09-25T09:00:00Z',
          actor: 'user',
          field_id: 'x',
          on_revision: 1,
          action: 'correct',
          before: {},
          after: {},
        },
      }
      setRoute(`POST ${J}/fields/f-registru/decide`, reply)
      setRoute(`POST ${J}/fields/f-annual/decide`, reply)
      const missing = page.getByTestId('missing-row-f-registru')
      await missing.getByRole('button', { name: 'Scrie valoarea' }).click()
      await missing.getByRole('textbox').fill('J00/000/2000')
      await missing.getByRole('button', { name: 'Salvează' }).click()
      await settle(page)
      const text = requests.find((item) => item.path === `${J}/fields/f-registru/decide`)
      assert.deepEqual(text.body, {
        action: 'correct',
        on_revision: REGISTRU.revision,
        value: 'J00/000/2000',
      })

      const row = page.getByTestId('conflict-row-f-annual')
      await row.getByRole('button', { name: 'Scrie altă valoare' }).click()
      await row.getByRole('textbox').fill('abc')
      await row.getByRole('button', { name: 'Salvează' }).click()
      await row.getByText('Valoarea nu este un număr.').waitFor()
      assert.equal(count(requests, 'POST', `${J}/fields/f-annual/decide`), 0)
      await row.getByRole('textbox').fill('22 163,5')
      await row.getByRole('button', { name: 'Salvează' }).click()
      await settle(page)
      const number = requests.find((item) => item.path === `${J}/fields/f-annual/decide`)
      assert.deepEqual(number.body, { action: 'correct', on_revision: 3, value: '22163.5' })
    },
  )
})

test('B10 evidence: a cell chip and a calculated chip, each evidence fetched once', async () => {
  await withHarness({ path: `/app/piee/${JOB}/date?camp=f-annual` }, async ({ page, requests }) => {
    const grid = page.getByTestId('carrier-table-electricity_grid')
    await grid.getByRole('button', { name: /Prelucrare · Consum Electric!D11/ }).click()
    const detail = page.getByTestId('evidence-detail').first()
    await detail.waitFor()
    assert.match(await detail.innerText(), /Consum Electric!D11/)
    await detail.getByText('Exemplu - Prelucrare date 2023-2025.xlsx').waitFor()
    const row = page.getByTestId('conflict-row-f-annual')
    await row.getByRole('button', { name: 'calculat' }).click()
    await row.getByText('calculat · 3 intrări').waitFor()
    await settle(page)
    const evidence = requests.filter((item) => item.path.startsWith('/evidence/'))
    assert.equal(new Set(evidence.map((item) => item.path)).size, evidence.length)
    assert.ok(evidence.every((item) => item.path.endsWith('/quote')))
  })
})

test('B11 E1 reads the documents; import_required shows the widget and disables generation', async () => {
  await withHarness(
    {
      routes: {
        [`GET ${J}/fields`]: { status: 200, body: [] },
        [`GET ${J}/fields?status=missing`]: { status: 200, body: [] },
        [`POST ${J}/piee/import`]: {
          status: 202,
          body: { run_id: 'run-import-2', stage: 'piee_import', state: 'running' },
        },
        [`GET ${J}/events`]: {
          status: 200,
          contentType: 'text/event-stream',
          body: eventStream([
            { run_id: 'run-import-2', stage: 'piee_import', type: 'stage_started' },
            {
              run_id: 'run-import-2',
              stage: 'piee_import',
              type: 'stage_finished',
              payload: { state: 'ready', publication: 'current' },
            },
          ]),
        },
      },
    },
    async ({ page, requests }) => {
      await page.getByText('Datele nu au fost citite încă').waitFor()
      await page.getByRole('button', { name: 'Citeşte documentele' }).click()
      await settle(page)
      const post = requests.find((item) => item.path === `${J}/piee/import`)
      assert.deepEqual(post.body, { on_revision: 7 })
    },
  )
  const stale = {
    ...CHECKS,
    readiness: {
      ...CHECKS.readiness,
      blocking: [
        ...CHECKS.readiness.blocking,
        { code: 'import_required', message: 'Documentele trebuie citite din nou.' },
      ],
    },
  }
  await withHarness(
    { routes: { [`GET ${J}/export/checks`]: { status: 200, body: stale } } },
    async ({ page }) => {
      await page.getByText('Documentele s-au schimbat').waitFor()
      const generate = page.getByRole('button', { name: 'Generează programul' })
      assert.equal(await generate.isDisabled(), true)
      assert.equal(await generate.getAttribute('title'), 'Citeşte întâi documentele.')
    },
  )
})
