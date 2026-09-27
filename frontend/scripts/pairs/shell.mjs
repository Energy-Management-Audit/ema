import { OVERVIEW } from '../../tests/fixtures/base.mjs'
import { focusCheck, line } from '../s17b-checks.mjs'

const finalized = [0, 1, 2].map((index) => ({
  ...OVERVIEW[0],
  id: `finished-${String(index)}`,
  year: 2022 + index,
  updated_at: `2026-09-27T08:0${String(index)}:00Z`,
  approved_at: `2026-09-27T08:0${String(index)}:00Z`,
  finalized: true,
}))

export const PAIRS = [
  {
    id: 'M1-sidebar',
    refs: { light: ['missing', '#M1 .win aside'], dark: ['missing', '#M1 .win aside'] },
    path: '/app/clienti',
    ours: '.ema-sidebar',
  },
  {
    id: '3e-sidebar',
    refs: { light: ['hifi', '[id="3e"] [data-screen-label] aside'] },
    path: '/app/clienti',
    ours: '.ema-sidebar',
    routes: { 'GET /jobs/overview': { status: 200, body: [...OVERVIEW, ...finalized] } },
  },
  {
    id: '7c-new',
    refs: { light: ['system', '[id="7c"] > div:nth-of-type(2)'] },
    path: '/app/clienti',
    ours: '.ema-dialog',
    async act(page) {
      await page.getByRole('button', { name: 'Lucrare nouă' }).click()
      await page.getByRole('dialog').waitFor()
    },
  },
]

export async function checks(page, label, pair, theme, viewport) {
  const width = await page
    .locator('.ema-sidebar')
    .evaluate((element) => element.getBoundingClientRect().width)
  const results = [line(Math.abs(width - 230) <= 1, `${label}: sidebar 230`, `${String(width)}px`)]
  if (pair.id === '7c-new') {
    const box = await page.getByRole('dialog').boundingBox()
    const select = await page.getByRole('combobox').boundingBox()
    const year = await page.getByRole('textbox').boundingBox()
    results.push(
      line(
        Boolean(box && box.x >= 0 && box.x + box.width <= viewport.width),
        `${label}: dialog fits`,
      ),
      line(
        Boolean(select && year && Math.abs(select.width - year.width) <= 1),
        `${label}: client select fills row`,
      ),
    )
  } else if (pair.id === '3e-sidebar') {
    results.push(
      line(
        (await page.locator('.ema-nav-group').last().locator('.ema-nav-job').count()) === 1 &&
          (await page.getByRole('button', { name: 'încă două…' }).count()) === 1,
        `${label}: finalized collapsed to one recent job`,
      ),
    )
  } else if (theme === 'light' && viewport.width === 1400) {
    results.push(
      await focusCheck(
        page,
        `${label} Lucrare nouă`,
        page.getByRole('button', { name: 'Lucrare nouă' }),
      ),
    )
  }
  return results
}
