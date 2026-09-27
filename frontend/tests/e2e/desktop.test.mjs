import assert from 'node:assert/strict'
import test from 'node:test'
import { JOB } from '../fixtures/piee/default.mjs'
import { withHarness } from './helpers.mjs'

const outputPath = `/jobs/${JOB}/outputs/out-draft-1`

for (const result of ['saved', 'cancelled']) {
  test(`3i desktop ${result} uses Save As bridge without an error notice`, async () => {
    await withHarness({ path: `/app/piee/${JOB}/documente` }, async ({ page, requests }) => {
      await page.addInitScript(() => {
        window.__desktopCalls = []
        window.pywebview = {
          api: {
            save_output: (jobId, outputId) => {
              window.__desktopCalls.push([jobId, outputId])
              return new Promise((resolve) => {
                window.__finishDesktopSave = resolve
              })
            },
            open_output: async () => ({ ok: true, result: 'opened' }),
          },
        }
      })
      await page.reload()
      const before = requests.filter((request) => request.path === outputPath).length
      const row = page.getByTestId('output-row-out-draft-1')
      const button = row.getByRole('button', { name: 'Descarcă' })
      await button.click()
      await page.waitForFunction(() =>
        document
          .querySelector('[data-testid="output-row-out-draft-1"] button')
          ?.hasAttribute('data-loading'),
      )
      await page.evaluate(
        (value) => window.__finishDesktopSave({ ok: true, result: value }),
        result,
      )
      await page.waitForFunction(
        () =>
          !document
            .querySelector('[data-testid="output-row-out-draft-1"] button')
            ?.hasAttribute('data-loading'),
      )
      assert.deepEqual(await page.evaluate(() => window.__desktopCalls), [[JOB, 'out-draft-1']])
      assert.equal(await row.getByRole('alert').count(), 0)
      assert.equal(requests.filter((request) => request.path === outputPath).length, before)
    })
  })
}

test('3i browser download still requests output bytes', async () => {
  await withHarness({ path: `/app/piee/${JOB}/documente` }, async ({ page }) => {
    const outputRequest = page.waitForRequest(
      (request) => new URL(request.url()).pathname === outputPath,
    )
    await page
      .getByTestId('output-row-out-draft-1')
      .getByRole('button', { name: 'Descarcă' })
      .click()
    assert.equal(new URL((await outputRequest).url()).pathname, outputPath)
  })
})

test('3i desktop stale output refetches the listed outputs', async () => {
  await withHarness({ path: `/app/piee/${JOB}/documente` }, async ({ page }) => {
    await page.addInitScript(() => {
      window.pywebview = {
        api: {
          save_output: async () => ({
            ok: false,
            code: 'output_stale',
            message: 'Documentul a fost modificat extern.',
          }),
          open_output: async () => ({ ok: true, result: 'opened' }),
        },
      }
    })
    await page.reload()
    await page.getByTestId('output-row-out-draft-1').waitFor()
    await page.waitForLoadState('networkidle')
    const refetch = page.waitForRequest(
      (request) =>
        request.method() === 'GET' && new URL(request.url()).pathname === `/jobs/${JOB}/outputs`,
    )
    await page
      .getByTestId('output-row-out-draft-1')
      .getByRole('button', { name: 'Descarcă' })
      .click()
    await refetch
    await page.getByText('Documentul a fost modificat extern.').waitFor()
  })
})

test('3i desktop unexpected bridge error shows the save failure', async () => {
  await withHarness({ path: `/app/piee/${JOB}/documente` }, async ({ page }) => {
    await page.addInitScript(() => {
      window.pywebview = {
        api: {
          save_output: async () => {
            throw new Error('synthetic dialog failure')
          },
          open_output: async () => ({ ok: true, result: 'opened' }),
        },
      }
    })
    await page.reload()
    await page
      .getByTestId('output-row-out-draft-1')
      .getByRole('button', { name: 'Descarcă' })
      .click()
    await page.getByText('Fişierul nu s-a putut salva.').waitFor()
  })
})
