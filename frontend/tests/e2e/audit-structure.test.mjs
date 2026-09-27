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
      await scope.getByRole('button', { name: 'Marchează gata' }).click()
      await page.waitForResponse((response) => response.url().endsWith(`/sections/${drafted.id}`))
      assert.deepEqual(
        requests.find((item) => item.path.endsWith(`/sections/${drafted.id}`)).body,
        { status: 'done', on_revision: drafted.revision, confirm: true },
      )
      const proposedRow = page
        .locator('.audit-section-row')
        .filter({ hasText: 'Obiective urmărite' })
      await proposedRow.getByRole('button', { name: 'Confirmă „nu se aplică”' }).click()
      await page.waitForResponse((response) => response.url().endsWith(`/sections/${proposed.id}`))
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
      await row.getByRole('button', { name: 'Confirmă „nu se aplică”' }).click()
      await page.waitForResponse((response) => response.url().endsWith('/sections/ch1.obiective'))
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
      await page.getByRole('textbox', { name: 'Notiţa ta' }).blur()
      await page.waitForResponse((response) => response.url().endsWith('/audit/notes/ch1'))
      assert.deepEqual(requests.find((item) => item.path.endsWith('/audit/notes/ch1')).body, {
        text: 'Verifică',
        on_revision: 0,
      })
      await page.getByRole('button', { name: 'Stabileşte termenul' }).click()
      await page.getByRole('textbox', { name: 'Termen client' }).fill('01.12.2026')
      await page.getByRole('button', { name: 'Salvează' }).click()
      await page.waitForResponse((response) => response.url().endsWith('/audit/deadline'))
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
