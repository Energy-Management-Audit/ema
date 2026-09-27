import {
  J,
  JOB,
  acceptedBatch,
  acceptedIdentity,
  confirmedChecks,
  invoiceRoutes,
} from '../../tests/fixtures/invoices/default.mjs'
import { focusCheck, line } from '../s17b-checks.mjs'

const tableRoutes = {
  ...invoiceRoutes,
  [`GET ${J}/invoices/identity`]: { status: 200, body: acceptedIdentity },
  [`GET ${J}/invoices`]: { status: 200, body: acceptedBatch },
  [`GET ${J}/export/checks`]: { status: 200, body: confirmedChecks },
}
const readableRoutes = {
  ...tableRoutes,
  [`GET ${J}/invoices`]: {
    status: 200,
    body: {
      ...acceptedBatch,
      files: acceptedBatch.files.filter((file) => file.status !== 'failed'),
    },
  },
}

export const PAIRS = [
  {
    id: '3f',
    refs: {
      light: ['hifi', '[id="3f"] [data-screen-label]'],
      dark: ['hifi', '[id="3f"] [data-screen-label]'],
    },
    path: `/app/facturi/${JOB}`,
    routes: readableRoutes,
    ours: '.ema-window',
    activity: true,
    async act(page) {
      await page.getByRole('button', { name: 'Vezi octombrie' }).click()
      await page
        .locator('.invoice-open')
        .evaluate((element) => element.scrollIntoView({ block: 'center' }))
    },
  },
  {
    id: 'M7',
    refs: { light: ['missing', '#M7 .win'], dark: ['missing', '#M7 .win'] },
    path: `/app/facturi/${JOB}`,
    routes: invoiceRoutes,
    ours: '.ema-window',
    activity: true,
  },
  {
    id: '3f-missing',
    refs: {
      light: ['hifi', '[id="3f"] [data-screen-label]'],
      dark: ['hifi', '[id="3f"] [data-screen-label]'],
    },
    path: `/app/facturi/${JOB}`,
    routes: readableRoutes,
    ours: '.ema-window',
    activity: true,
    async act(page) {
      await page.getByRole('row').filter({ hasText: 'factura lipseşte' }).scrollIntoViewIfNeeded()
    },
  },
  {
    id: '7b-failed',
    refs: {
      light: ['system', '[id="7b"] > div:nth-of-type(2)'],
      dark: ['system', '[id="7b"] > div:nth-of-type(2)'],
    },
    path: `/app/facturi/${JOB}`,
    routes: tableRoutes,
    ours: '.invoice-table .ema-card',
    activity: true,
  },
]

export async function checks(page, label, pair, theme, viewport) {
  const results = []
  if (theme === 'light' && viewport.width === 1400) {
    if (pair.id === 'M7')
      results.push(
        await focusCheck(
          page,
          `${label} Confirmă clientul`,
          page.getByRole('button', { name: 'Confirmă clientul' }),
        ),
      )
    if (pair.id === '3f') {
      results.push(
        await focusCheck(
          page,
          `${label} Exportă Excel`,
          page.getByRole('button', { name: 'Exportă Excel' }),
        ),
      )
      results.push(
        await focusCheck(
          page,
          `${label} SourceButton`,
          page.getByRole('button', { name: /PDF · pag./ }).first(),
        ),
      )
    }
  }
  if (pair.id === '3f') {
    results.push(
      line(
        (await page.locator('.invoice-open__paper img').count()) === 1,
        `${label}: page image in open row`,
      ),
    )
  }
  if (pair.id === '3f-missing') {
    results.push(
      line(
        (await page.getByRole('row').filter({ hasText: 'factura lipseşte' }).count()) === 1,
        `${label}: missing month has its own row`,
      ),
    )
    results.push(
      line(
        (await page.locator('.invoice-activity__progress[role="progressbar"]').count()) === 1,
        `${label}: annual progress bar`,
      ),
    )
  }
  if (pair.id === '7b-failed') {
    results.push(
      line(
        (await page.getByRole('list', { name: 'Starea fişierelor' }).count()) === 1,
        `${label}: file status list`,
      ),
    )
  }
  return results
}
