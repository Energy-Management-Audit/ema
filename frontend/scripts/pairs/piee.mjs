import {
  FINAL_OUTPUTS,
  FINAL_CHECKS,
  JOB,
  eventStream,
} from '../../tests/fixtures/piee/default.mjs'
const J = `/jobs/${JOB}`
const option = (id) => `[id="${id}"] > div:nth-of-type(2)`
const screen = (id) => `[id="${id}"] [data-screen-label]`
const running = eventStream([
  {
    run_id: 'run-gen-9',
    stage: 'piee_generate',
    type: 'stage_started',
    payload: { state: 'running' },
  },
  {
    run_id: 'run-gen-9',
    stage: 'piee_generate',
    type: 'stage_progress',
    payload: { done: 1, total: 2, message: 'Ciornă generată' },
  },
])
const runningStatus = {
  id: JOB,
  type: 'piee',
  state: 'running',
  revision: 8,
  runs: [{ id: 'run-gen-9', stage: 'piee_generate', state: 'running' }],
}
const failedStatus = {
  id: JOB,
  type: 'piee',
  state: 'failed',
  revision: 9,
  runs: [{ id: 'run-gen-9', stage: 'piee_generate', state: 'failed', error: 'Etapa a eşuat.' }],
}
const exportRoutes = {
  [`GET ${J}/outputs`]: { status: 200, body: FINAL_OUTPUTS },
  [`GET ${J}/export/checks`]: { status: 200, body: FINAL_CHECKS },
}

// Each pair: the reference per theme (null where the handoff draws only one theme) and our state.
export const PAIRS = [
  {
    id: 'M6',
    refs: { light: ['missing', '#M6 .win'], dark: ['missing', '#M6 .win'] },
    path: `/app/piee/${JOB}/documente`,
    activity: true,
  },
  {
    id: 'M4',
    refs: { light: ['missing', '#M4 .win'], dark: ['missing', '#M4 .win'] },
    path: `/app/piee/${JOB}/date`,
    activity: true,
  },
  {
    id: '3c',
    refs: { light: ['hifi', screen('3c')] },
    path: `/app/piee/${JOB}/date?camp=f-annual`,
    activity: true,
  },
  {
    id: 'M5',
    refs: { light: ['missing', '#M5 .win'], dark: ['missing', '#M5 .win'] },
    path: `/app/piee/${JOB}/date?camp=f-annual`,
    activity: true,
    async act(page) {
      const row = page.getByTestId('conflict-row-f-annual')
      await row.getByRole('button', { name: 'calculat' }).click()
      await row.getByRole('button', { name: 'Vezi intrările' }).click()
    },
  },
  {
    id: '3g-6c',
    refs: { light: ['hifi', screen('3g')], dark: ['dark', screen('6c')] },
    path: `/app/piee/${JOB}/masuri`,
    activity: true,
    async act(page) {
      await page
        .getByTestId('measure-row-measure.planned.2')
        .locator('.measure-row__source')
        .click()
    },
  },
  {
    id: '7a',
    refs: { light: ['system', screen('7a')] },
    path: `/app/piee/${JOB}/predare`,
    routes: exportRoutes,
  },
  {
    id: '7b-R1',
    refs: { light: ['system', option('7b')] },
    path: `/app/piee/${JOB}/date`,
    activity: true,
    routes: {
      [`GET ${J}/status`]: { status: 200, body: runningStatus },
      [`GET ${J}/events`]: { status: 200, contentType: 'text/event-stream', body: running },
    },
  },
  {
    id: '7b-R2',
    refs: { light: ['system', option('7b')] },
    path: `/app/piee/${JOB}/date`,
    activity: true,
    routes: { [`GET ${J}/status`]: { status: 200, body: failedStatus } },
  },
]
