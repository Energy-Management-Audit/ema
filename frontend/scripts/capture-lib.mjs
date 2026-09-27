import {
  createReadStream,
  existsSync,
  mkdirSync,
  readFileSync,
  statSync,
  writeFileSync,
} from 'node:fs'
import { createServer } from 'node:http'
import { extname, join, normalize, resolve, sep } from 'node:path'
import { chromium } from 'playwright'
import { startHarness } from '../tests/e2e/harness.mjs'
import { focusCheck, fontChecks, layoutChecks, line, paperChecks } from './s17b-checks.mjs'

const reference = process.env.EMA_REFERENCE
if (!reference)
  throw new Error('EMA_REFERENCE is not set; the handoff lives in $EMA_REFERENCE/design.')
const designRoot = resolve(reference, 'design')
const pages = {
  hifi: 'handoff-2026-09-21/EMA Hi-Fi.dc.html',
  dark: 'handoff-2026-09-21/EMA Dark.dc.html',
  system: 'handoff-2026-09-21/EMA Design System.dc.html',
  missing: 'missing-screens-2026-09-24/EMA Missing Screens.html',
}
const types = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
}
export function serveDesign() {
  const server = createServer((request, response) => {
    const path = normalize(
      join(designRoot, decodeURIComponent(new URL(request.url, 'http://x').pathname)),
    )
    if (!path.startsWith(designRoot + sep) || !existsSync(path) || !statSync(path).isFile()) {
      response.writeHead(404).end()
      return
    }
    response.writeHead(200, { 'content-type': types[extname(path)] ?? 'application/octet-stream' })
    createReadStream(path).pipe(response)
  })
  return new Promise((done) => {
    server.listen(0, '127.0.0.1', () => {
      done({ server, url: `http://127.0.0.1:${String(server.address().port)}` })
    })
  })
}

export async function settle(page) {
  await page.waitForLoadState('networkidle')
  await page.evaluate(() => document.fonts.ready)
  await page.waitForTimeout(300)
}

export async function referenceShots(browser, designUrl, pairs, out) {
  const shots = {}
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } })
  for (const theme of ['light', 'dark']) {
    for (const pair of pairs) {
      const ref = pair.refs[theme]
      if (!ref) continue
      const file = `ref-${theme}-${pair.id}.png`
      await page.goto(`${designUrl}/${encodeURI(pages[ref[0]])}`, { waitUntil: 'networkidle' })
      if (ref[0] === 'missing' && theme === 'dark')
        await page.evaluate(() => document.body.classList.add('theme-dark'))
      await settle(page)
      const target = page.locator(ref[1]).first()
      await target.scrollIntoViewIfNeeded()
      await target.screenshot({ path: join(out, file), animations: 'disabled' })
      shots[`${theme}-${pair.id}`] = file
    }
  }
  await page.close()
  return shots
}

export async function ourShots(theme, viewport, report, pairs, out, extraChecks) {
  const shots = {}
  const suffix = viewport.width === 1400 ? '' : `-${String(viewport.width)}`
  for (const pair of pairs) {
    const label = `${theme} ${String(viewport.width)}×${String(viewport.height)} ${pair.id}`
    const harness = await startHarness({
      theme,
      viewport,
      routes: pair.routes ?? {},
      path: pair.path,
    })
    try {
      const { page } = harness
      await page.locator('.ema-window').waitFor()
      await settle(page)
      if (pair.act) await pair.act(page, theme)
      await settle(page)
      const file = `ours-${theme}-${pair.id}${suffix}.png`
      await (pair.ours ? page.locator(pair.ours) : page).screenshot({
        path: join(out, file),
        animations: 'disabled',
      })
      shots[`${theme}-${pair.id}`] = file
      report.push(...(await layoutChecks(page, label, pair, viewport)))
      report.push(...(await fontChecks(page, label)))
      if (extraChecks) report.push(...(await extraChecks(page, label, pair, theme, viewport)))
      if (theme === 'dark') report.push(...(await paperChecks(page, label)))
      if (theme === 'light' && viewport.width === 1400) {
        if (pair.id === 'M4') {
          report.push(
            await focusCheck(
              page,
              `${label} Generează programul`,
              page.getByRole('button', { name: 'Generează programul' }),
            ),
          )
          report.push(
            await focusCheck(page, `${label} a tab`, page.getByRole('tab', { name: /Măsuri/ })),
          )
          report.push(
            await focusCheck(
              page,
              `${label} a SourceChip`,
              page.locator('.ema-source-chip').first(),
            ),
          )
        }
        if (pair.id === '7a') {
          report.push(
            await focusCheck(
              page,
              `${label} Aprobă şi exportă`,
              page.getByRole('button', { name: 'Aprobă şi exportă' }),
            ),
          )
        }
      }
      if (theme === 'dark' && pair.id === '3g-6c') {
        await page.getByTestId('measure-row-measure.planned.2').getByRole('textbox').waitFor()
        report.push(...(await paperChecks(page, `${label} with an editor`)))
      }
    } finally {
      try {
        await harness.close()
        report.push(line(true, `${label}: no request outside the app origin, no console message`))
      } catch (error) {
        report.push(
          line(
            false,
            `${label}: no request outside the app origin, no console message`,
            error.message,
          ),
        )
      }
    }
  }
  return shots
}

export async function pairImage(browser, left, right, title, file, out) {
  const page = await browser.newPage({ viewport: { width: 2900, height: 900 } })
  const image = (name) =>
    `data:image/png;base64,${readFileSync(join(out, name)).toString('base64')}`
  const reference = left
    ? `<figure style="margin:0"><figcaption>reference</figcaption><img src="${image(left)}"></figure>`
    : '<figure style="margin:0"><figcaption>reference: none in this theme</figcaption></figure>'
  await page.setContent(`<body style="margin:0;padding:20px;background:#fff;font:13px system-ui">
    <p style="margin:0 0 12px">${title} · <b>visual review pending</b></p>
    <div style="display:flex;gap:20px;align-items:flex-start">${reference}
      <figure style="margin:0"><figcaption>Ema (S17b)</figcaption><img src="${image(right)}"></figure>
    </div></body>`)
  await page.waitForLoadState('load')
  await page.screenshot({ path: join(out, file), fullPage: true })
  await page.close()
  return file
}

export async function runCapture({ area, pairs, out, extraChecks }) {
  mkdirSync(out, { recursive: true })
  const design = await serveDesign()
  const browser = await chromium.launch()
  const report = []
  const pairFiles = []
  try {
    const refs = await referenceShots(browser, design.url, pairs, out)
    for (const theme of ['light', 'dark']) {
      const ours = await ourShots(
        theme,
        { width: 1400, height: 900 },
        report,
        pairs,
        out,
        extraChecks,
      )
      for (const item of pairs) {
        pairFiles.push(
          await pairImage(
            browser,
            refs[`${theme}-${item.id}`],
            ours[`${theme}-${item.id}`],
            `${item.id} (${theme})`,
            `pair-${theme}-${item.id}.png`,
            out,
          ),
        )
      }
      await ourShots(theme, { width: 1280, height: 800 }, report, pairs, out, extraChecks)
    }
  } finally {
    await browser.close()
    design.server.close()
  }

  const failed = report.filter((item) => item.startsWith('FAIL'))
  const lines = [
    `S17b ${area} visual acceptance — visual review pending (the coordinator compares the pairs).`,
    `summary: ${String(report.length - failed.length)} PASS, ${String(failed.length)} FAIL, ${String(pairFiles.length)} pairs`,
    '',
    ...report,
    '',
    `pairs in ${out}`,
    ...pairFiles.map((file) => `  ${file}`),
  ]
  writeFileSync(join(out, 'checks.txt'), `${lines.join('\n')}\n`)
  writeFileSync(
    join(out, 'index.html'),
    `<!doctype html><meta charset="utf-8"><title>S17b pairs</title><body style="font:13px system-ui">
  <h1>S17b — visual review pending</h1><pre>${lines.join('\n')}</pre>
  ${pairFiles.map((file) => `<p>${file}</p><img src="${file}" style="max-width:100%">`).join('\n')}</body>`,
  )
  console.log(lines.join('\n'))
  process.exitCode = failed.length ? 1 : 0
}
