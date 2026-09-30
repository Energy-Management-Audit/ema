import assert from 'node:assert/strict'
import test from 'node:test'
import { JOB, OUTLINE, routes } from '../fixtures/audit/default.mjs'
import { withHarness } from './helpers.mjs'
import { problem } from './harness.mjs'

const J = `/jobs/${JOB.id}`

test('chapter actions send status, confirmation, reason and section revision', async () => {
  const drafted = OUTLINE.nodes.find((node) => node.id === 'ch1.scop')
  const proposed = OUTLINE.nodes.find((node) => node.id === 'ch1.obiective')
  await withHarness(
    {
      path: `/app/audit/${JOB.id}/structura`,
      routes: {
        ...routes,
        [`PATCH ${J}/sections/${drafted.id}`]: { body: drafted },
        [`PATCH ${J}/sections/${proposed.id}`]: { body: proposed },
      },
    },
    async ({ page, requests }) => {
      await page.getByRole('button', { name: 'Deschide' }).first().click()
      const scope = page.locator('.audit-section-row').filter({ hasText: 'Scopul auditului' })
      const scoped = page.waitForResponse(
        (response) =>
          response.request().method() === 'PATCH' &&
          response.url().endsWith(`/sections/${drafted.id}`),
      )
      await scope.getByRole('button', { name: 'Marchează gata' }).click()
      await scoped
      assert.deepEqual(
        requests.find((item) => item.path.endsWith(`/sections/${drafted.id}`)).body,
        { status: 'done', on_revision: drafted.revision, confirm: true },
      )
      const proposedRow = page
        .locator('.audit-section-row')
        .filter({ hasText: 'Obiective urmărite' })
      const proposedSaved = page.waitForResponse(
        (response) =>
          response.request().method() === 'PATCH' &&
          response.url().endsWith(`/sections/${proposed.id}`),
      )
      await proposedRow.getByRole('button', { name: 'Confirmă „nu se aplică”' }).click()
      await proposedSaved
      assert.deepEqual(
        requests.find((item) => item.path.endsWith(`/sections/${proposed.id}`)).body,
        { status: 'n/a', on_revision: proposed.revision, reason: proposed.reason, confirm: true },
      )
      const applies = page.waitForResponse((response) =>
        response.url().endsWith(`/sections/${proposed.id}`),
      )
      await proposedRow.getByRole('button', { name: 'Se aplică', exact: true }).click()
      await applies
      assert.deepEqual(
        requests.filter((item) => item.path.endsWith(`/sections/${proposed.id}`)).at(-1).body,
        { status: 'ready', on_revision: proposed.revision },
      )
      assert.equal(
        requests.some((item) => item.path.includes('/draft')),
        false,
      )
    },
  )
})

test('exclusion requires a reason, later uses allowed reason, note and deadline save', async () => {
  const rows = structuredClone(OUTLINE)
  rows.nodes.find((node) => node.id === 'ch1.obiective').status = 'missing'
  await withHarness(
    {
      path: `/app/audit/${JOB.id}/structura`,
      routes: {
        ...routes,
        [`GET ${J}/audit/outline`]: { body: rows },
        [`PATCH ${J}/sections/ch1.obiective`]: { body: rows.nodes[2] },
        [`PUT ${J}/audit/notes/ch1`]: {
          body: { section_id: 'ch1', text: 'Verifică', revision: 1 },
        },
        [`PUT ${J}/audit/deadline`]: { body: { deadline: '2026-12-01', revision: 1 } },
      },
    },
    async ({ page, requests }) => {
      await page.getByRole('button', { name: 'Deschide' }).first().click()
      const row = page.locator('.audit-section-row').filter({ hasText: 'Obiective urmărite' })
      await row.getByRole('button', { name: 'Scoate din raport' }).click()
      assert.equal(
        await row.getByRole('button', { name: 'Confirmă „nu se aplică”' }).isDisabled(),
        true,
      )
      await row.getByRole('textbox', { name: 'Motiv' }).fill('Nu există procesul')
      const excluded = page.waitForResponse(
        (response) =>
          response.request().method() === 'PATCH' &&
          response.url().endsWith('/sections/ch1.obiective'),
      )
      await row.getByRole('button', { name: 'Confirmă „nu se aplică”' }).click()
      await excluded
      assert.equal(
        requests.find((item) => item.path.endsWith('/sections/ch1.obiective')).body.reason,
        'Nu există procesul',
      )
      await row.getByRole('button', { name: 'Mai târziu' }).click()
      await row.getByRole('combobox').selectOption('visit')
      const laterSaved = page.waitForResponse((response) =>
        response.url().endsWith('/sections/ch1.obiective'),
      )
      await row.getByRole('button', { name: 'Salvează' }).click()
      await laterSaved
      assert.deepEqual(
        requests.filter((item) => item.path.endsWith('/sections/ch1.obiective')).at(-1).body,
        { status: 'later', on_revision: rows.nodes[2].revision, reason: 'visit' },
      )
      await page.getByRole('textbox', { name: 'Notiţa ta' }).fill('Verifică')
      const noteSaved = page.waitForResponse(
        (response) =>
          response.request().method() === 'PUT' && response.url().endsWith('/audit/notes/ch1'),
      )
      await page.getByRole('textbox', { name: 'Notiţa ta' }).blur()
      await noteSaved
      assert.deepEqual(requests.find((item) => item.path.endsWith('/audit/notes/ch1')).body, {
        text: 'Verifică',
        on_revision: 0,
      })
      await page.getByRole('button', { name: 'Stabileşte termenul' }).click()
      await page.getByRole('textbox', { name: 'Termen client' }).fill('01.12.2026')
      const deadlineSaved = page.waitForResponse(
        (response) =>
          response.request().method() === 'PUT' && response.url().endsWith('/audit/deadline'),
      )
      await page.getByRole('button', { name: 'Salvează' }).click()
      await deadlineSaved
      assert.deepEqual(requests.find((item) => item.path.endsWith('/audit/deadline')).body, {
        deadline: '2026-12-01',
        on_revision: 0,
      })
      await page.getByRole('button', { name: 'Stabileşte termenul' }).click()
      const clearing = page.waitForResponse((response) =>
        response.url().endsWith('/audit/deadline'),
      )
      await page.getByRole('button', { name: 'Şterge' }).click()
      await clearing
      assert.deepEqual(
        requests.filter((item) => item.path.endsWith('/audit/deadline')).at(-1).body,
        { deadline: null, on_revision: 0 },
      )
    },
  )
})

test('note conflict stays visible and refreshes outline', async () => {
  await withHarness(
    {
      path: `/app/audit/${JOB.id}/structura`,
      routes: {
        ...routes,
        [`PUT ${J}/audit/notes/ch3`]: problem(
          'stale_revision',
          409,
          'Notiţa a fost modificată între timp.',
        ),
      },
    },
    async ({ page }) => {
      await page.getByRole('textbox', { name: 'Notiţa ta' }).fill('Nouă')
      await page.getByRole('textbox', { name: 'Notiţa ta' }).blur()
      await page.getByRole('alert').getByText('Notiţa a fost modificată între timp.').waitFor()
    },
  )
})

test('3j chapter confirmation sends every drafted node with its revision', async () => {
  const outline = structuredClone(OUTLINE)
  outline.nodes.find((node) => node.id === 'ch1').status = 'drafted'
  const drafted = outline.nodes.filter((node) => node.chapter === 1 && node.status === 'drafted')
  await withHarness(
    {
      path: `/app/audit/${JOB.id}/structura`,
      routes: {
        ...routes,
        [`GET ${J}/audit/outline`]: { body: outline },
        [`PATCH ${J}/sections`]: { body: drafted.map((node) => ({ ...node, status: 'done' })) },
      },
    },
    async ({ page, requests }) => {
      await page.getByRole('button', { name: 'Deschide' }).first().click()
      const confirm = page.getByRole('button', { name: 'Marchează ca pregătit' })
      assert.equal(await confirm.isDisabled(), false)
      const patched = page.waitForResponse((response) => response.url().endsWith(`${J}/sections`))
      const refreshed = page.waitForResponse((response) =>
        response.url().endsWith(`${J}/audit/outline`),
      )
      await confirm.click()
      await patched
      await refreshed
      assert.deepEqual(
        requests.find((item) => item.path === `${J}/sections`).body,
        drafted.map((node) => ({
          section_id: node.id,
          status: 'done',
          on_revision: node.revision,
          confirm: true,
        })),
      )
      assert.ok(requests.filter((item) => item.path === `${J}/audit/outline`).length >= 2)
    },
  )
})

test('3j chapter confirmation is disabled without drafted nodes', async () => {
  const outline = structuredClone(OUTLINE)
  outline.nodes.find((node) => node.id === 'ch1.scop').status = 'done'
  await withHarness(
    {
      path: `/app/audit/${JOB.id}/structura`,
      routes: { ...routes, [`GET ${J}/audit/outline`]: { body: outline } },
    },
    async ({ page, requests }) => {
      await page.getByRole('button', { name: 'Deschide' }).first().click()
      assert.equal(
        await page.getByRole('button', { name: 'Marchează ca pregătit' }).isDisabled(),
        true,
      )
      assert.equal(
        requests.some((item) => item.path === `${J}/sections`),
        false,
      )
    },
  )
})

test('3j stale chapter confirmation refetches and names the newly stale drafted nodes', async () => {
  const updated = structuredClone(OUTLINE)
  updated.nodes.find((node) => node.id === 'ch1.scop').stale = true
  await withHarness(
    {
      path: `/app/audit/${JOB.id}/structura`,
      routes: {
        ...routes,
        [`PATCH ${J}/sections`]: problem('sections_stale', 409, 'Unele secţiuni au ciorna veche.'),
      },
    },
    async ({ page, requests, setRoute }) => {
      await page.getByRole('button', { name: 'Deschide' }).first().click()
      setRoute(`GET ${J}/audit/outline`, { body: updated })
      await page.getByRole('button', { name: 'Marchează ca pregătit' }).click()
      await page.getByRole('alert').getByText('Ciorna e veche la: Scopul auditului.').waitFor()
      assert.ok(requests.filter((item) => item.path === `${J}/audit/outline`).length >= 2)
    },
  )
})

test('3j revision conflict refetches the outline and shows the prescribed message', async () => {
  await withHarness(
    {
      path: `/app/audit/${JOB.id}/structura`,
      routes: {
        ...routes,
        [`PATCH ${J}/sections`]: problem(
          'stale_revision',
          409,
          'Secţiunea s-a modificat între timp.',
        ),
      },
    },
    async ({ page, requests }) => {
      await page.getByRole('button', { name: 'Deschide' }).first().click()
      await page.getByRole('button', { name: 'Marchează ca pregătit' }).click()
      await page.getByRole('alert').getByText('Secţiunea s-a modificat între timp.').waitFor()
      assert.ok(requests.filter((item) => item.path === `${J}/audit/outline`).length >= 2)
    },
  )
})
