import { OVERVIEW } from '../../tests/fixtures/base.mjs'
import { CLIENT_ROUTES } from '../../tests/fixtures/clients/default.mjs'
import { REPORT_ROUTES } from '../../tests/fixtures/clients/reporting.mjs'
import { focusCheck } from '../s17b-checks.mjs'

const ref = (id) =>
  id === '7c-delete' ? ['system', '[id="7c"] > div:nth-of-type(2)'] : ['missing', `#${id} .win`]

export const PAIRS = [
  {
    id: 'M1',
    refs: { light: ref('M1'), dark: ref('M1') },
    path: '/app/clienti',
    routes: CLIENT_ROUTES,
  },
  {
    id: 'M2',
    refs: { light: ref('M2'), dark: ref('M2') },
    path: '/app/clienti/client-exemplu/date',
    routes: CLIENT_ROUTES,
    activity: true,
  },
  {
    id: 'M3',
    refs: { light: ref('M3'), dark: ref('M3') },
    path: '/app/raportare',
    routes: REPORT_ROUTES,
    activity: true,
  },
  {
    id: '7c-delete',
    refs: { light: ref('7c-delete'), dark: ref('7c-delete') },
    path: '/app/clienti/client-exemplu/lucrari',
    routes: {
      ...CLIENT_ROUTES,
      'GET /jobs/overview': { status: 200, body: OVERVIEW },
      'GET /jobs/job-piee-1/slots': { status: 200, body: ['anexa', 'prelucrare', 'questionnaire'] },
      'GET /jobs/job-piee-1/fields': { status: 200, body: [{ id: 'field-a' }, { id: 'field-b' }] },
    },
    activity: true,
    ours: '.ema-dialog',
    async act(page) {
      await page
        .locator('.client-list__row', { hasText: 'PIEE 2026' })
        .getByRole('button', { name: 'Şterge' })
        .click()
      await page.getByRole('dialog').waitFor()
      await page.getByText('Se şterg 3 fişiere').waitFor()
    },
  },
]

export async function checks(page, label, pair, theme, viewport) {
  if (theme !== 'light' || viewport.width !== 1400) return []
  if (pair.id === 'M1')
    return [
      await focusCheck(
        page,
        `${label} Client nou după CUI`,
        page.getByRole('button', { name: 'Client nou după CUI' }),
      ),
      await focusCheck(page, `${label} filter tab`, page.getByRole('tab', { name: /Fără anexă/ })),
    ]
  if (pair.id === 'M3')
    return [
      await focusCheck(
        page,
        `${label} Generează raportul`,
        page.getByRole('button', { name: 'Generează raportul' }),
      ),
    ]
  return []
}
