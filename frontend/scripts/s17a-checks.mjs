// Deterministic S17a checks, run on the rendered component sheet: token values per theme, the
// focus ring, paper that never inverts, toggle and row states, bundled fonts.

const readme = {
  light: {
    surface: '#f6f2e8',
    'surface-sunken': '#f0ebde',
    'surface-raised': '#f1ecdf',
    'surface-accent': '#f3ead6',
    paper: '#fffdf6',
    ink: '#252219',
    'ink-muted': 'rgba(37,34,25,.72)',
    border: 'rgba(37,34,25,.11)',
    olive: '#4f7015',
    amber: '#b8751a',
    error: '#9e3f1f',
    violet: '#7a5ea8',
  },
  dark: {
    surface: '#1e1b16',
    'surface-sunken': '#181510',
    'surface-raised': '#242019',
    'surface-accent': '#2a2419',
    paper: '#fffdf6',
    ink: '#ece5d5',
    'ink-muted': 'rgba(236,229,213,.72)',
    border: 'rgba(236,229,213,.11)',
    olive: '#9bbb52',
    amber: '#d8a24e',
    error: '#e8836a',
    violet: '#a58cd4',
  },
}

function line(ok, what, detail) {
  return `${ok ? 'PASS' : 'FAIL'} ${what}${detail ? ` — ${detail}` : ''}`
}

/** Resolves colours through the browser, so `#f6f2e8` and `var(--surface)` compare equal. */
function colourProbe(page, frameSelector) {
  return (value) =>
    page.evaluate(
      ([selector, colour]) => {
        const probe = document.createElement('span')
        probe.style.background = colour
        document.querySelector(selector).append(probe)
        const resolved = getComputedStyle(probe).backgroundColor
        probe.remove()
        return resolved
      },
      [frameSelector, value],
    )
}

async function tokens(page, theme, frame) {
  const resolve = colourProbe(page, frame)
  const results = []
  for (const [name, expected] of Object.entries(readme[theme])) {
    const actual = await resolve(`var(--${name})`)
    const wanted = await resolve(expected)
    results.push(
      line(actual === wanted, `${theme}: --${name} = ${expected}`, actual === wanted ? '' : actual),
    )
  }
  return results
}

async function paper(page, theme) {
  const found = await page.evaluate(() =>
    [...document.querySelectorAll('.ema-paper, .ema-field')].map((element) => {
      const style = getComputedStyle(element)
      return {
        bg: style.backgroundColor,
        ink: style.getPropertyValue('--ink').trim(),
        cls: element.className,
      }
    }),
  )
  const bad = found.filter(({ bg }) => bg !== 'rgb(255, 253, 246)')
  const inverted = found.filter(({ cls, ink }) => cls.includes('ema-paper') && ink !== '#252219')
  return [
    line(
      found.length > 0 && bad.length === 0,
      `${theme}: paper surfaces and fields stay #fffdf6 (${String(found.length)})`,
      bad.map((b) => b.cls).join(', '),
    ),
    line(inverted.length === 0, `${theme}: content inside paper keeps the light ink`),
  ]
}

async function focusRing(page, theme) {
  const expected =
    theme === 'dark'
      ? 'rgb(30, 27, 22) 0px 0px 0px 2px, rgb(155, 187, 82) 0px 0px 0px 4px'
      : 'rgb(246, 242, 232) 0px 0px 0px 2px, rgb(79, 112, 21) 0px 0px 0px 4px'
  await page.evaluate(() => {
    document.activeElement?.blur()
    window.scrollTo(0, 0)
  })
  let shadow = ''
  for (let step = 0; step < 40 && !shadow; step += 1) {
    await page.keyboard.press('Tab')
    shadow = await page.evaluate(() => {
      const active = document.activeElement
      return active?.classList.contains('ema-btn') ? getComputedStyle(active).boxShadow : ''
    })
  }
  const field = await page.evaluate(() => {
    const input = document.querySelector('.ema-field:not([data-state])')
    input.focus()
    const style = getComputedStyle(input)
    const result = {
      border: style.borderTopColor,
      width: style.borderTopWidth,
      shadow: style.boxShadow,
    }
    input.blur()
    return result
  })
  const olive = theme === 'dark' ? 'rgb(155, 187, 82)' : 'rgb(79, 112, 21)'
  return [
    line(
      shadow === expected,
      `${theme}: keyboard focus on a button draws surface 2px + olive 2px`,
      shadow === expected ? '' : shadow,
    ),
    line(
      // 1.5px is snapped to one device pixel at DPR 1, in the handoff as here.
      field.border === olive &&
        ['1px', '1.5px'].includes(field.width) &&
        field.shadow.includes('0px 0px 0px 3px'),
      `${theme}: focused input has the 1.5px olive border and the 3px olive ring`,
      `${field.border} ${field.width} ${field.shadow}`,
    ),
  ]
}

async function states(page, theme, frame) {
  const resolve = colourProbe(page, frame)
  const results = []
  const toggle = page.locator(`[data-theme="${theme}"] [role="switch"]`).first()
  const before = await toggle.evaluate((element) => ({
    checked: element.getAttribute('aria-checked'),
    bg: getComputedStyle(element).backgroundColor,
    knob:
      element.firstElementChild.getBoundingClientRect().left - element.getBoundingClientRect().left,
  }))
  await toggle.click()
  const after = await toggle.evaluate((element) => ({
    checked: element.getAttribute('aria-checked'),
    bg: getComputedStyle(element).backgroundColor,
    knob:
      element.firstElementChild.getBoundingClientRect().left - element.getBoundingClientRect().left,
  }))
  await toggle.click()
  const olive = await resolve('var(--olive)')
  const off = await resolve('rgb(var(--ink-rgb) / 0.16)')
  results.push(
    line(
      before.checked === 'true' &&
        before.bg === olive &&
        before.knob === 19 &&
        after.checked === 'false' &&
        after.bg === off &&
        after.knob === 2,
      `${theme}: toggle 40×23 — on olive with the knob right, off ink 16 % with the knob left`,
      `${JSON.stringify(before)} → ${JSON.stringify(after)}`,
    ),
  )

  const row = await page
    .locator(`${frame} .ema-list-row[aria-selected="true"]`)
    .first()
    .evaluate((element) => ({
      bg: getComputedStyle(element).backgroundColor,
      shadow: getComputedStyle(element).boxShadow,
    }))
  const selected = await resolve('rgb(var(--olive-rgb) / 0.12)')
  results.push(
    line(
      row.bg === selected && row.shadow === `${olive} 2px 0px 0px 0px inset`,
      `${theme}: selected row is olive 12 % with a 2px inset bar`,
      JSON.stringify(row),
    ),
  )

  const primary = page
    .locator(`${frame} .ema-btn--primary:not([data-state]):not(:disabled)`)
    .first()
  await primary.hover()
  const hovered = await primary.evaluate((element) => getComputedStyle(element).backgroundColor)
  await page.mouse.move(0, 0)
  results.push(
    line(
      hovered === (await resolve('var(--primary-hover)')),
      `${theme}: primary hover fill`,
      hovered,
    ),
  )

  const disabled = await page
    .locator(`${frame} .ema-btn:disabled`)
    .first()
    .evaluate((element) => {
      const style = getComputedStyle(element)
      return {
        bg: style.backgroundColor,
        color: style.color,
        shadow: style.boxShadow,
        cursor: style.cursor,
      }
    })
  const disabledOk =
    disabled.bg === (await resolve('rgb(var(--ink-rgb) / 0.1)')) &&
    disabled.color === (await resolve('rgb(var(--ink-rgb) / 0.4)')) &&
    disabled.shadow === 'none' &&
    disabled.cursor === 'default'
  results.push(
    line(
      disabledOk,
      `${theme}: disabled button — ink 10 % fill, 40 % label, no shadow, no pointer`,
      JSON.stringify(disabled),
    ),
  )
  return results
}

async function fonts(page, theme) {
  const loaded = await page.evaluate(async () => {
    await document.fonts.ready
    return [...document.fonts]
      .filter((face) => face.status === 'loaded')
      .map((face) => face.family.replaceAll('"', ''))
  })
  return [
    line(
      loaded.includes('Geist') && loaded.includes('Geist Mono'),
      `${theme}: Geist and Geist Mono loaded from the bundle`,
      loaded.join(', '),
    ),
  ]
}

export async function runChecks(page, theme) {
  const frame = theme === 'dark' ? '#sheet-7e' : '#sheet-7d'
  return [
    ...(await tokens(page, theme, frame)),
    ...(await paper(page, theme)),
    ...(await focusRing(page, theme)),
    ...(await states(page, theme, frame)),
    ...(await fonts(page, theme)),
  ]
}
