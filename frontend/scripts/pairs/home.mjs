import { OVERVIEW } from '../../tests/fixtures/base.mjs'
import { focusCheck, line } from '../s17b-checks.mjs'

const settings = {
  theme: 'light',
  default_provider: 'gemini',
  providers: {
    gemini: {
      present: true,
      verified_at: '2026-09-27T08:00:00Z',
      hint: 'AIza••••••••7Kd2',
      source: 'keyring',
    },
    openai: { present: false, verified_at: null, hint: null, source: null },
  },
  extraction: { ocr: true, flag_uncertain: true, auto_accept_exact: false },
  workspace: '/synthetic/workspace',
  backup: {
    dir: '/synthetic/backups',
    last_at: '2026-09-18T08:00:00Z',
    last_size: 1024,
    last_name: 'ema-backup-synthetic.zip',
    due: true,
  },
}
const baseRoutes = { 'GET /jobs/overview': { body: OVERVIEW }, 'GET /settings': { body: settings } }
const themeAct = async (page, theme) => {
  await page.evaluate((value) => {
    document.documentElement.dataset.theme = value
  }, theme)
}

export const PAIRS = [
  {
    id: '3e',
    refs: { light: ['hifi', '[id="3e"] [data-screen-label]'] },
    path: '/app/',
    ours: '.ema-window',
    routes: baseRoutes,
    act: themeAct,
  },
  {
    id: '6a',
    refs: { dark: ['dark', '[id="6a"] [data-screen-label]'] },
    path: '/app/',
    ours: '.ema-window',
    routes: baseRoutes,
    act: themeAct,
  },
  {
    id: '3i',
    refs: { light: ['hifi', '[id="3i"] [data-screen-label]'] },
    path: '/app/setari/extragere',
    ours: '.ema-window',
    routes: { 'GET /settings': { body: settings } },
    act: themeAct,
  },
  {
    id: '7b-new',
    refs: { light: ['system', '[id="7b"] > div:nth-of-type(2)'] },
    path: '/app/',
    ours: '.ema-window',
    routes: { ...baseRoutes, 'GET /jobs/overview': { body: [] } },
    act: themeAct,
  },
]

export async function checks(page, label, pair, theme, viewport) {
  const measured = await page.evaluate(() => ({
    sidebar: document.querySelector('.ema-sidebar')?.getBoundingClientRect().width,
    inner: document
      .querySelector('.home-screen__inner, .settings-screen__inner')
      ?.getBoundingClientRect().width,
  }))
  const expected = pair.id === '3i' ? 720 : 760
  const results = [
    line(Math.abs(measured.sidebar - 230) <= 1, `${label}: sidebar 230`, String(measured.sidebar)),
    line(
      measured.inner <= expected && measured.inner >= Math.min(expected, viewport.width - 310),
      `${label}: content width`,
      String(measured.inner),
    ),
  ]
  if (theme === 'light' && viewport.width === 1400 && pair.id === '3e') {
    results.push(
      await focusCheck(
        page,
        `${label} Lucrare nouă`,
        page.locator('.home-screen').getByRole('button', { name: 'Lucrare nouă' }),
      ),
    )
  }
  if (theme === 'light' && viewport.width === 1400 && pair.id === '3i') {
    results.push(
      await focusCheck(
        page,
        `${label} Toggle`,
        page.getByRole('switch', { name: 'OCR pentru documente scanate' }),
      ),
    )
    await page.getByLabel('Cheie OpenAI').fill('synthetic')
    results.push(
      await focusCheck(page, `${label} Adaugă`, page.getByRole('button', { name: 'Adaugă' })),
    )
  }
  return results
}
