import assert from 'node:assert/strict'
import test from 'node:test'
import { DOCUMENTS, FIELDS, JOB, routes } from '../fixtures/audit/default.mjs'
import { withHarness } from './helpers.mjs'

test('audit document, review, structure and readings tabs stay in one job shell', async () => {
  await withHarness(
    {
      path: `/app/audit/${JOB.id}/documente`,
      routes: {
        ...routes,
        // s17b-audit-report: Raport Word and Predare read the report, approvals and sections.
        [`GET /jobs/${JOB.id}/audit/report`]: { body: { draft: null, final: null, word: true } },
        [`GET /jobs/${JOB.id}/approvals`]: { body: [] },
        [`GET /jobs/${JOB.id}/sections`]: { body: [] },
      },
    },
    async ({ page, requests }) => {
      await page.getByRole('heading', { name: 'Audit energetic 2026' }).waitFor()
      assert.match(await page.getByRole('tab', { name: /Documente/ }).innerText(), /8/)
      assert.match(
        await page.getByRole('tab', { name: /Structura raportului/ }).innerText(),
        /0\/2/,
      )
      assert.match(await page.getByRole('tab', { name: /Revizuire/ }).innerText(), /2/)
      await page.getByText('Dosarul clientului').waitFor()
      assert.ok((await page.getByText('1. Facturi.pdf', { exact: true }).count()) >= 1)
      await page.getByRole('tab', { name: /Revizuire/ }).click()
      await page.getByText('Numele societăţii').waitFor()
      await page.getByRole('tab', { name: /Structura raportului/ }).click()
      await page.getByText('CE ŢINE CAPITOLUL PE LOC').waitFor()
      await page.getByRole('tab', { name: /Măsurători/ }).click()
      await page.getByText('Nu sunt valori citite.').first().waitFor()
      await page.getByRole('button', { name: 'Previzualizare' }).click()
      await page.waitForURL(`**/app/audit/${JOB.id}/raport`)
      await page.goto(page.url().replace('/raport', '/documente'))
      await page.getByRole('button', { name: 'Exportă Word' }).click()
      await page.waitForURL(`**/app/audit/${JOB.id}/predare`)
      assert.equal(
        requests.some((item) => item.path.endsWith('/piee/summary')),
        false,
      )
    },
  )
})

test('Măsurători tab is absent until the job has visit material', async () => {
  await withHarness(
    {
      path: `/app/audit/${JOB.id}/documente`,
      routes: {
        ...routes,
        [`GET /jobs/${JOB.id}/audit/documents`]: { body: { ...DOCUMENTS, visit: null } },
        [`GET /jobs/${JOB.id}/fields`]: { body: FIELDS },
      },
    },
    async ({ page }) => {
      await page.getByRole('tab', { name: /Documente/ }).waitFor()
      assert.equal(await page.getByRole('tab', { name: /Măsurători/ }).count(), 0)
    },
  )
})
