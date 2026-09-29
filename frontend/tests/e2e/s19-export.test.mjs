import assert from 'node:assert/strict'
import test from 'node:test'
import {
  FINAL_CHECKS as AUDIT_CHECKS,
  FINAL_OUTPUTS as AUDIT_OUTPUTS,
  FINAL_RUN,
  REPORT,
  J as AUDIT_J,
  JOB as AUDIT_JOB,
  EXPORTED as AUDIT_EXPORTED,
  reportRoutes,
} from '../fixtures/audit-report/default.mjs'
import {
  FINAL_CHECKS as PIEE_CHECKS,
  FINAL_OUTPUTS as PIEE_OUTPUTS,
  EXPORTED as PIEE_EXPORTED,
  JOB as PIEE_JOB,
} from '../fixtures/piee/default.mjs'
import { problem } from './harness.mjs'
import { count, withHarness } from './helpers.mjs'

const cases = [
  {
    path: `/app/audit/${AUDIT_JOB}/predare`,
    J: AUDIT_J,
    checks: AUDIT_CHECKS,
    outputs: AUDIT_OUTPUTS,
    response: AUDIT_EXPORTED,
    routes: {
      ...reportRoutes,
      [`GET ${AUDIT_J}/audit/report`]: { body: { ...REPORT, final: FINAL_RUN } },
    },
  },
  {
    path: `/app/piee/${PIEE_JOB}/predare`,
    J: `/jobs/${PIEE_JOB}`,
    checks: PIEE_CHECKS,
    outputs: PIEE_OUTPUTS,
    response: PIEE_EXPORTED,
    routes: {},
  },
]

for (const item of cases) {
  const routes = {
    ...item.routes,
    [`GET ${item.J}/export/checks`]: { body: item.checks },
    [`GET ${item.J}/outputs`]: { body: item.outputs },
  }
  test(`O1/O2 ${item.path}: a newer draft leaves the server-selected final exportable and downloadable`, async () => {
    const final = item.outputs.find((file) => file.id === item.checks.final.output_id)
    const newer = {
      ...final,
      id: 'newer-draft',
      kind: 'draft',
      version: 99,
      run_id: 'new-draft-run',
      name: 'New-draft.docx',
      stage: item.J === AUDIT_J ? 'audit_render' : 'piee_generate',
    }
    await withHarness(
      {
        path: item.path,
        routes: {
          ...routes,
          [`GET ${item.J}/outputs`]: { body: [...item.outputs, newer] },
          [`POST ${item.J}/export`]: { body: item.response },
          [`GET ${item.J}/outputs/${final.id}`]: {
            body: 'PK synthetic final',
            contentType: final.media_type,
          },
        },
      },
      async ({ page, requests }) => {
        await page.getByRole('button', { name: 'Aprobă şi exportă', exact: true }).click()
        await page
          .getByText(`Fişierele finale sunt în ${item.response.folder}`, { exact: true })
          .waitFor()
        assert.deepEqual(
          requests.find(
            (request) => request.method === 'POST' && request.path === `${item.J}/export`,
          ).body,
          {
            output_id: final.id,
            readiness_hash: item.checks.readiness_hash,
            confirm: true,
            dest_dir: null,
          },
        )
        for (const file of item.response.files)
          await page.getByText(`${file.name} · ${file.path}`, { exact: true }).waitFor()
        const downloading = page.waitForEvent('download')
        await page.getByRole('button', { name: 'Descarcă doar Word' }).click()
        assert.equal((await downloading).suggestedFilename(), final.name)
        assert.equal(count(requests, 'GET', `${item.J}/outputs/newer-draft`), 0)
      },
    )
  })

  test(`O2 ${item.path}: desktop cancellation sends nothing; a chosen folder is passed verbatim`, async () => {
    await withHarness(
      {
        path: item.path,
        routes: { ...routes, [`POST ${item.J}/export`]: { body: item.response } },
      },
      async ({ page, requests }) => {
        await page.evaluate(() => {
          window.pywebview = { api: { choose_folder: async () => null } }
        })
        const button = page.getByRole('button', { name: 'Aprobă şi exportă', exact: true })
        await button.click()
        await button.evaluate(
          (node) =>
            new Promise((resolve) => {
              const check = () => {
                if (!node.hasAttribute('data-loading')) resolve()
                else requestAnimationFrame(check)
              }
              check()
            }),
        )
        assert.equal(count(requests, 'POST', `${item.J}/export`), 0)
        await page.evaluate(() => {
          window.pywebview.api.choose_folder = async () => ({ path: 'C:\\Audits\\Chosen folder' })
        })
        await button.click()
        await page
          .getByText(`Fişierele finale sunt în ${item.response.folder}`, { exact: true })
          .waitFor()
        assert.equal(
          requests.find((request) => request.path === `${item.J}/export`).body.dest_dir,
          'C:\\Audits\\Chosen folder',
        )
      },
    )
  })

  test(`O2 ${item.path}: an approved final can retry a copy failure after reload`, async () => {
    let copies = 0
    const approval = {
      id: 'approved-1',
      output_id: item.checks.final.output_id,
      readiness_hash: item.checks.readiness_hash,
      at: item.response.approved_at,
    }
    await withHarness(
      {
        path: item.path,
        routes: {
          ...routes,
          [`GET ${item.J}/approvals`]: { body: [approval] },
          [`POST ${item.J}/export`]: () =>
            ++copies === 1
              ? problem('output_changed', 500, 'Copierea a eşuat.')
              : { body: item.response },
        },
      },
      async ({ page, requests }) => {
        await page.getByText(/^Aprobat /).waitFor()
        await page.getByRole('button', { name: 'Aprobă şi exportă', exact: true }).click()
        await page.getByRole('alert').getByText('Copierea a eşuat.').waitFor()
        await page.reload()
        await page.getByText(/^Aprobat /).waitFor()
        await page.getByRole('button', { name: 'Aprobă şi exportă', exact: true }).click()
        await page
          .getByText(`Fişierele finale sunt în ${item.response.folder}`, { exact: true })
          .waitFor()
        const posts = requests.filter(
          (request) => request.method === 'POST' && request.path === `${item.J}/export`,
        )
        assert.equal(posts.length, 2)
        assert.deepEqual(posts[0].body, posts[1].body)
      },
    )
  })

  test(`O1 ${item.path}: local final outputs cannot override checks.final null`, async () => {
    await withHarness(
      {
        path: item.path,
        routes: {
          ...routes,
          [`GET ${item.J}/export/checks`]: { body: { ...item.checks, final: null } },
        },
      },
      async ({ page }) => {
        await page
          .getByRole('button', {
            name: item.J === AUDIT_J ? 'Generează versiunea finală' : 'Generează pachetul',
            exact: true,
          })
          .waitFor()
        assert.equal(
          await page.getByRole('button', { name: 'Aprobă şi exportă', exact: true }).count(),
          0,
        )
      },
    )
  })
}

test('O2 returned destination paths wrap within the Predare column', async () => {
  const item = cases[1]
  const folder = 'C:\\' + 'ClientFolder'.repeat(25)
  const receipt = {
    ...item.response,
    folder,
    files: item.response.files.map((file) => ({ ...file, path: `${folder}\\${file.name}` })),
  }
  await withHarness(
    {
      path: item.path,
      viewport: { width: 1280, height: 800 },
      routes: {
        [`GET ${item.J}/outputs`]: { body: item.outputs },
        [`GET ${item.J}/export/checks`]: { body: item.checks },
        [`POST ${item.J}/export`]: { body: receipt },
      },
    },
    async ({ page }) => {
      await page.getByRole('button', { name: 'Aprobă şi exportă', exact: true }).click()
      await page.getByText(`Fişierele finale sunt în ${folder}`, { exact: true }).waitFor()
      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
        false,
      )
    },
  )
})
