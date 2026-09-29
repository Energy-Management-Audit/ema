// S17b audit-report pairs (D10 visual): 3d running on chapter 4 over a previous draft, 7a for an
// audit at X3, and the 7c regenerate dialog. The references are the handoff's own screens.

import {
  FINAL_OUTPUTS,
  FINAL_CHECKS,
  FINAL_RUN,
  J,
  JOB,
  ANSWERED,
  REPORT,
  eventStream,
  reportRoutes,
} from '../../tests/fixtures/audit-report/default.mjs'
import { focusCheck, line } from '../s17b-checks.mjs'

const screen = (id) => `[id="${id}"] [data-screen-label]`
const running = {
  ...reportRoutes,
  [`GET ${J}`]: { status: 200, body: { ...reportRoutes[`GET ${J}`].body, state: 'running' } },
  [`GET ${J}/status`]: {
    status: 200,
    body: {
      id: JOB,
      type: 'audit',
      state: 'running',
      revision: 2,
      runs: [{ id: 'run-draft-2', stage: 'audit_render', state: 'running' }],
    },
  },
  [`GET ${J}/events`]: {
    status: 200,
    contentType: 'text/event-stream',
    body: eventStream([
      { run_id: 'run-draft-2', stage: 'audit_render', type: 'stage_started', payload: {} },
      {
        run_id: 'run-draft-2',
        stage: 'audit_render',
        type: 'stage_progress',
        payload: {
          done: 3,
          total: 6,
          message:
            'Capitolul 4 din 6 — Analiza modului în care se realizează consumurile energetice pe platforma societății',
        },
      },
    ]),
  },
}

export const PAIRS = [
  {
    id: '3d',
    refs: { light: ['hifi', screen('3d')] },
    path: `/app/audit/${JOB}/raport`,
    routes: running,
    activity: true,
    async act(page) {
      await page.getByTestId('report-progress').waitFor()
      await page.locator('.report-page__canvas').first().waitFor()
    },
  },
  {
    id: '7a-audit',
    refs: { light: ['system', screen('7a')] },
    path: `/app/audit/${JOB}/predare`,
    routes: {
      ...reportRoutes,
      [`GET ${J}/outputs`]: { status: 200, body: FINAL_OUTPUTS },
      [`GET ${J}/export/checks`]: { status: 200, body: FINAL_CHECKS },
      [`GET ${J}/sections`]: { status: 200, body: ANSWERED },
      [`GET ${J}/audit/report`]: { status: 200, body: { ...REPORT, final: FINAL_RUN } },
    },
    async act(page) {
      await page.getByRole('button', { name: 'Aprobă şi exportă' }).waitFor()
    },
  },
]

export async function checks(page, label, pair, theme, viewport) {
  const results = []
  if (pair.id === '3d') {
    const frames = await page
      .getByTestId('pdf-page')
      .evaluateAll((nodes) => nodes.map((node) => getComputedStyle(node).backgroundColor))
    results.push(
      line(
        frames.length > 0 && frames.every((value) => value === 'rgb(255, 253, 246)'),
        `${label}: every PdfPages frame is paper`,
        frames.join(' '),
      ),
    )
    const toc = await page
      .getByTestId('report-toc')
      .evaluate((node) => node.getBoundingClientRect().width)
    results.push(line(Math.abs(toc - 220) <= 1, `${label}: CUPRINS 220`, `${String(toc)}px`))
    if (theme === 'light' && viewport.width === 1400) {
      results.push(
        await focusCheck(
          page,
          `${label} Descarcă`,
          page.getByTestId('report-panel').getByRole('button', { name: 'Descarcă' }),
        ),
      )
    }
  }
  if (pair.id === '7a-audit' && theme === 'light' && viewport.width === 1400) {
    results.push(
      await focusCheck(
        page,
        `${label} Aprobă şi exportă`,
        page.getByRole('button', { name: 'Aprobă şi exportă' }),
      ),
    )
  }
  return results
}
