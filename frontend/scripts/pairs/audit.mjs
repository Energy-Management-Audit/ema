import { DOCUMENTS, FIELDS, JOB, routes } from '../../tests/fixtures/audit/default.mjs'
import { FULL_OUTLINE } from '../../tests/fixtures/audit/full-outline.mjs'
import { eventStream } from '../../tests/fixtures/piee/default.mjs'
import { focusCheck, line } from '../s17b-checks.mjs'

const J = `/jobs/${JOB.id}`
const screen = (id) => `[id="${id}"] [data-screen-label]`
const option = (id) => `[id="${id}"] > div:nth-of-type(2)`
const stale = structuredClone(DOCUMENTS)
stale.runs.read.current = false
const accepted = FIELDS.map((field) => ({ ...field, review: 'accepted' }))
const catalogueRoutes = { ...routes, [`GET ${J}/audit/outline`]: { body: FULL_OUTLINE } }
const documentView = structuredClone(DOCUMENTS)
documentView.files[0].item_text = 'Necesar info · datele societăţii'
documentView.files[5].item_text = 'Consum gaz 2023–25 · energie electrică'
const reviewDecision = {
  id: 'synthetic-accept',
  field_id: FIELDS[1].id,
  action: 'accept',
  target_kind: 'field',
  at: '2026-09-27T08:00:00Z',
  actor: 'user',
  on_revision: 1,
  before: FIELDS[1],
  after: { ...FIELDS[1], review: 'accepted' },
  batch_id: null,
  undone_by: null,
}
const online = {
  ...FIELDS[0],
  id: 'online-1',
  label: 'Factor online',
  state: 'enriched',
  evidence: ['online-1'],
}
const calc = {
  ...FIELDS[1],
  id: 'calc-1',
  label: 'Economie calculată',
  state: 'calculated',
  confidence: 'exact',
  evidence: ['calc-1'],
  derivation: { formula_id: 'sum', inputs: [], factor_version: '2026' },
}

export const PAIRS = [
  {
    id: '3b-6b',
    refs: { light: ['hifi', screen('3b')], dark: ['dark', screen('6b')] },
    path: `/app/audit/${JOB.id}/documente`,
    activity: true,
    routes: { ...routes, [`GET ${J}/audit/documents`]: { body: documentView } },
  },
  {
    id: '3b-drop',
    refs: { light: ['hifi', screen('3b')], dark: ['dark', screen('6b')] },
    path: `/app/audit/${JOB.id}/documente`,
    activity: true,
    routes,
    async act(page) {
      await page.locator('.audit-drop').scrollIntoViewIfNeeded()
    },
  },
  {
    id: '3b-reading',
    refs: { light: ['hifi', screen('3b')], dark: ['dark', screen('6b')] },
    path: `/app/audit/${JOB.id}/documente`,
    activity: true,
    routes: {
      ...routes,
      [`GET ${J}/audit/documents`]: { body: stale },
      [`POST ${J}/stages/read`]: {
        status: 202,
        body: { run_id: 'audit-read', stage: 'read', state: 'running' },
      },
      [`GET ${J}/events`]: {
        contentType: 'text/event-stream',
        body: `retry: 600000\n${eventStream([
          {
            run_id: 'audit-read',
            stage: 'read',
            type: 'stage_started',
            at: new Date().toISOString(),
            payload: {},
          },
          {
            run_id: 'audit-read',
            stage: 'read',
            type: 'stage_progress',
            at: new Date().toISOString(),
            payload: { done: 2, total: 4, message: 'Citeşte documente' },
          },
        ])}`,
      },
    },
    async act(page) {
      await page.getByRole('button', { name: 'Extrage datele' }).click()
      await page.getByText('Citeşte documente').waitFor()
    },
  },
  {
    id: '3c',
    refs: { light: ['hifi', screen('3c')] },
    path: `/app/audit/${JOB.id}/revizuire?camp=${FIELDS[0].id}`,
    activity: true,
    routes: {
      ...routes,
      [`GET ${J}/fields`]: { body: [FIELDS[0], reviewDecision.after] },
      [`GET ${J}/log`]: { body: [reviewDecision] },
    },
    async act(page) {
      await page.getByRole('button', { name: 'Deschide pagina' }).waitFor()
    },
  },
  {
    id: 'M5',
    refs: { light: ['missing', '#M5 .win'], dark: ['missing', '#M5 .win'] },
    path: `/app/audit/${JOB.id}/revizuire`,
    activity: true,
    routes: {
      ...routes,
      [`GET ${J}/fields`]: { body: [online, calc] },
      'GET /evidence/online-1/quote': {
        body: {
          id: 'online-1',
          provenance: 'online',
          file_sha: null,
          locator: { kind: 'url', url: 'https://www.example.org/' },
          retrieved_at: '2026-09-27T08:00:00Z',
          quote: 'Factor online',
          highlight: 'exact',
        },
      },
      'GET /evidence/calc-1/quote': {
        body: {
          id: 'calc-1',
          provenance: 'calculated',
          file_sha: null,
          locator: null,
          retrieved_at: '2026-09-27T08:00:00Z',
          quote: '',
          highlight: 'exact',
        },
      },
    },
    async act(page) {
      await page
        .locator('.ema-review-row')
        .filter({ hasText: 'Factor online' })
        .locator('.ema-source-btn')
        .click()
      await page.getByText('PAGINĂ WEB · instantaneu salvat').waitFor()
    },
  },
  {
    id: '3j',
    refs: { light: ['hifi', screen('3j')] },
    path: `/app/audit/${JOB.id}/structura`,
    activity: true,
    routes: catalogueRoutes,
  },
  {
    id: 'M8',
    refs: { light: ['missing', '#M8 .win'], dark: ['missing', '#M8 .win'] },
    path: `/app/audit/${JOB.id}/structura`,
    activity: true,
    routes: catalogueRoutes,
    async act(page) {
      await page.getByRole('button', { name: 'Deschide' }).first().click()
    },
  },
  {
    id: '7b-review',
    refs: { light: ['system', option('7b')] },
    path: `/app/audit/${JOB.id}/revizuire`,
    activity: true,
    routes: { ...routes, [`GET ${J}/fields`]: { body: accepted } },
  },
  {
    id: '7c-rerun',
    refs: { light: ['system', option('7c')] },
    path: `/app/audit/${JOB.id}/documente`,
    activity: true,
    routes: {
      ...routes,
      [`GET ${J}/audit/documents`]: { body: stale },
      [`GET ${J}/fields`]: { body: [accepted[0]] },
    },
    async act(page) {
      await page.getByRole('button', { name: 'Extrage datele' }).click()
      await page.getByRole('dialog').waitFor()
    },
  },
]

export async function checks(page, label, pair, theme, viewport) {
  const result = []
  if (theme === 'light' && viewport.width === 1400 && pair.id === '3c') {
    result.push(
      await focusCheck(
        page,
        `${label} Acceptă`,
        page.getByRole('button', { name: 'Acceptă', exact: true }).first(),
      ),
    )
    result.push(await focusCheck(page, `${label} source`, page.locator('.ema-source-btn').first()))
  }
  if (theme === 'light' && viewport.width === 1400 && pair.id === 'M8')
    result.push(
      await focusCheck(
        page,
        `${label} Confirmă`,
        page.getByRole('button', { name: 'Confirmă „nu se aplică”' }).first(),
      ),
    )
  if (theme === 'light' && viewport.width === 1400 && pair.id === '3b-6b')
    result.push(
      await focusCheck(page, `${label} tab`, page.getByRole('tab', { name: /Revizuire/ })),
    )
  result.push(line((await page.locator('body').count()) === 1, `${label}: page rendered`))
  return result
}
