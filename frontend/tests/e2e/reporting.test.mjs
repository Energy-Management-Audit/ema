import assert from 'node:assert/strict'
import test from 'node:test'
import {
  REPORT_CLIENTS,
  REPORT_PREVIEW,
  REPORT_ROUTES,
  READY_RUN,
} from '../fixtures/clients/reporting.mjs'
import { withHarness } from './helpers.mjs'

const year = new Date().getFullYear() - 1

test('M3 empty state and annex import identify created and ignored files', async () => {
  await withHarness(
    {
      path: '/app/raportare',
      routes: {
        'GET /clients/overview': { status: 200, body: [] },
        'GET /reporting/runs': { status: 200, body: [] },
        'POST /clients/annexes': {
          status: 200,
          body: {
            imported: [
              {
                file_name: 'Anexa-Nou.xlsx',
                client_id: 'new',
                client_name: 'Client nou',
                year,
                sha: 'abc',
                created: true,
              },
            ],
            ignored: [
              { file_name: 'Anexa-Fara-CUI.xlsx', code: 'cui_missing', reason: 'CUI lipseşte' },
            ],
          },
        },
      },
    },
    async ({ page, requests }) => {
      await page.getByText('Registrul nu a fost generat încă').waitFor()
      await page.locator('input[type=file]').setInputFiles({
        name: 'Anexa-Nou.xlsx',
        mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        buffer: Buffer.from('synthetic'),
      })
      const dialog = page.getByRole('dialog', { name: 'Anexe adăugate' })
      await dialog.getByText(/Anexa-Nou.xlsx/).waitFor()
      await dialog.getByText(/client nou/).waitFor()
      await dialog.getByText(/Anexa-Fara-CUI.xlsx/).waitFor()
      const upload = requests.find(
        (item) => item.method === 'POST' && item.path === '/clients/annexes',
      )
      assert.match(upload?.headers['content-type'] ?? '', /multipart\/form-data/)
      assert.match(upload?.body ?? '', /name="files"/)
    },
  )
})

test('M3 limits years and clients, follows reporting events, previews and downloads', async () => {
  let started = false
  let finished = false
  await withHarness(
    {
      path: '/app/raportare',
      routes: {
        ...REPORT_ROUTES,
        'GET /reporting/runs': () => ({
          status: 200,
          body: started
            ? [
                {
                  ...READY_RUN,
                  state: finished ? 'ready' : 'running',
                  output_id: finished ? READY_RUN.output_id : null,
                },
              ]
            : [],
        }),
        'POST /reporting/runs': () => {
          started = true
          return { status: 202, body: { ...READY_RUN, state: 'running', output_id: null } }
        },
        'GET /jobs/report-job-1/events': () => {
          finished = true
          return {
            status: 200,
            contentType: 'text/event-stream',
            body: `event: stage_finished\ndata: ${JSON.stringify({ stage: 'reporting', payload: {} })}\n\n`,
          }
        },
      },
    },
    async ({ page, requests }) => {
      await page.getByRole('button', { name: 'Alege' }).click()
      const dialog = page.getByRole('dialog', { name: 'Alege clienţii' })
      await dialog.getByRole('button', { name: 'Niciunul' }).click()
      await dialog.getByText(REPORT_CLIENTS[0].name).click()
      await dialog.getByRole('button', { name: 'Gata' }).click()
      await page.getByRole('button', { name: String(year - 2) }).click()
      await page.getByRole('button', { name: 'Generează raportul' }).click()
      assert.deepEqual(
        requests.find((item) => item.method === 'POST' && item.path === '/reporting/runs')?.body,
        {
          years: [year - 1, year],
          client_ids: [REPORT_CLIENTS[0].id],
        },
      )
      await page.getByText('2 anexe citite · 2 cu observaţii').waitFor()
      await page.getByRole('button', { name: `${String(year)} · 2` }).waitFor()
      await page.getByText('Modernizare iluminat').waitFor()
      await page.getByText('45,20').waitFor()
      await page.locator('.report-preview').getByRole('button', { name: 'lipseşte' }).waitFor()
      await page.getByText('ATENŢIE').waitFor()
      await page.getByText('INFORMARE').waitFor()
      await page.getByText('Anexa 2–3 · D12').waitFor()
      await page.getByRole('button', { name: `${String(year)} · PRIMELE RÂNDURI` }).click()
      await page.getByRole('button', { name: `${String(year - 1)} · PRIMELE RÂNDURI` }).waitFor()
      await page.getByRole('button', { name: `${String(year - 1)} · PRIMELE RÂNDURI` }).click()
      assert.ok(requests.some((item) => item.path === '/jobs/report-job-1/events'))
      assert.ok(requests.some((item) => item.path === '/reporting/runs/report-run-1/preview'))
      assert.deepEqual(REPORT_PREVIEW.companies_per_year[String(year)], 2)
      const download = page.waitForEvent('download')
      await page.getByRole('button', { name: 'Deschide registrul' }).click()
      await download
      assert.ok(requests.some((item) => item.path === '/jobs/report-job-1/outputs/report-output-1'))
    },
  )
})
