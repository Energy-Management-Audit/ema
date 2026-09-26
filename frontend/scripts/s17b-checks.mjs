// S17b deterministic checks (D10): layout columns, page scroll, fonts, paper in dark, focus ring.

export const line = (ok, label, detail = '') =>
  `${ok ? 'PASS' : 'FAIL'} ${label}${!ok && detail ? ` — ${detail}` : ''}`

export async function layoutChecks(page, label, pair, viewport) {
  const results = []
  const measured = await page.evaluate(() => {
    const width = (selector) =>
      document.querySelector(selector)?.getBoundingClientRect().width ?? null
    const actions = [...document.querySelectorAll('.ema-content__actions > *')].filter(
      (node) => node.getBoundingClientRect().height > 0,
    )
    const tops = new Set(
      actions
        .filter((node) => !node.classList.contains('job-header-problem'))
        .map((node) =>
          Math.round(node.getBoundingClientRect().top + node.getBoundingClientRect().height / 2),
        ),
    )
    return {
      overflow: document.documentElement.scrollWidth - window.innerWidth,
      sidebar: width('.ema-sidebar'),
      activity: width('.ema-activity'),
      content: width('.ema-window > .ema-content'),
      centres: [...tops],
      grid: (() => {
        const head = document.querySelector('.measure-grid--head')
        return head ? getComputedStyle(head).gridTemplateColumns : null
      })(),
    }
  })
  results.push(
    line(
      measured.overflow <= 0,
      `${label}: no horizontal page scroll`,
      `${String(measured.overflow)}px`,
    ),
  )
  if (pair.activity) {
    const ok =
      Math.abs(measured.sidebar - 230) <= 1 &&
      Math.abs(measured.activity - 290) <= 1 &&
      Math.abs(measured.content - (viewport.width - 520)) <= 1
    results.push(line(ok, `${label}: columns 230 / viewport−520 / 290`, JSON.stringify(measured)))
  }
  if (measured.grid !== null) {
    results.push(
      line(
        measured.grid.endsWith('130px 120px 96px 118px 132px'),
        `${label}: 3g fixed columns`,
        measured.grid,
      ),
    )
  }
  if (viewport.width === 1280 && measured.centres.length > 0) {
    const spread = Math.max(...measured.centres) - Math.min(...measured.centres)
    results.push(
      line(spread <= 2, `${label}: header actions on one line`, measured.centres.join(',')),
    )
  }
  return results
}

export async function fontChecks(page, label) {
  const fonts = await page.evaluate(() => {
    const family = (selector) => {
      const node = document.querySelector(selector)
      return node ? getComputedStyle(node).fontFamily : null
    }
    return {
      numbers: family('td.carrier-table__n'),
      figures: family('.ema-kpi__value .ema-figures'),
      sizes: family('.slot-row__size, .ema-package-file__size'),
      measure: family('.measure-row__main .measure-row__n'),
      label: family('.ema-content__titles h1'),
    }
  })
  const results = []
  for (const [name, value] of Object.entries(fonts)) {
    if (value === null) continue
    const mono = name !== 'label'
    const ok = mono
      ? value.startsWith('"Geist Mono"')
      : value.startsWith('Geist') || value.startsWith('"Geist"')
    results.push(line(ok, `${label}: ${name} in ${mono ? 'Geist Mono' : 'Geist'}`, value))
  }
  return results
}

export async function paperChecks(page, label) {
  const colours = await page.evaluate(() =>
    [...document.querySelectorAll('.ema-doc-thumb__page, .ema-field, .ema-paper')].map(
      (node) => getComputedStyle(node).backgroundColor,
    ),
  )
  return colours.length === 0
    ? []
    : [
        line(
          colours.every((value) => value === 'rgb(255, 253, 246)'),
          `${label}: paper stays #fffdf6 in dark`,
          colours.join(' '),
        ),
      ]
}

export async function focusCheck(page, label, locator) {
  await page.keyboard.press('Tab')
  await locator.focus()
  const shadow = await locator.evaluate((node) => getComputedStyle(node).boxShadow)
  return line(/0px 0px 0px 2px.*0px 0px 0px 4px/.test(shadow), `${label}: focus ring`, shadow)
}
