// S17a visual acceptance: renders the dev component sheet in both themes and the handoff's
// matching options at 1400×900, writes paired screenshots to $EMA_ARTIFACTS/s17a/ (outside git)
// for the coordinator's side-by-side review, and asserts what can be checked deterministically.
//
//   EMA_REFERENCE=… EMA_ARTIFACTS=… npm run capture --prefix frontend [-- --out <dir>]

import {
  createReadStream,
  existsSync,
  mkdirSync,
  readFileSync,
  statSync,
  writeFileSync,
} from 'node:fs'
import { createServer as createHttpServer } from 'node:http'
import { homedir } from 'node:os'
import { extname, join, normalize, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'
import { createServer as createViteServer } from 'vite'
import { runChecks } from './s17a-checks.mjs'

const reference = process.env.EMA_REFERENCE
if (!reference)
  throw new Error('EMA_REFERENCE is not set; the handoff lives in $EMA_REFERENCE/design.')
const designRoot = resolve(reference, 'design')
if (!existsSync(join(designRoot, 'handoff-2026-09-21'))) {
  throw new Error(`No design handoff under ${designRoot}`)
}
const artifacts = process.env.EMA_ARTIFACTS ?? join(homedir(), 'Code/projects/ema/artifacts')
const outFlag = process.argv.indexOf('--out')
const out = outFlag > 0 ? resolve(process.argv[outFlag + 1]) : join(artifacts, 's17a')
mkdirSync(out, { recursive: true })

const viewport = { width: 1400, height: 900 }
const frontendRoot = fileURLToPath(new URL('..', import.meta.url))

// Reference pages, and the element holding each option.
const handoff = 'handoff-2026-09-21'
const pages = {
  system: `${handoff}/EMA Design System.dc.html`,
  hifi: `${handoff}/EMA Hi-Fi.dc.html`,
  missing: 'missing-screens-2026-09-24/EMA Missing Screens.html',
}
const option = (id) => `[id="${id}"] > div:nth-of-type(2)`
const screen = (id) => `[id="${id}"] [data-screen-label]`

// Each extension row of the sheet, with the handoff region it reproduces. The handoff draws these
// screens in light only; the M-screens also carry the dark token set (.theme-dark).
const extensions = [
  { name: 'shell', refs: [['hifi', screen('3c'), '3c']] },
  { name: 'review', refs: [['hifi', screen('3c'), '3c']] },
  { name: 'settings', refs: [['hifi', screen('3i'), '3i']] },
  { name: 'sources', refs: [['missing', '#M5 .win', 'M5']] },
  {
    name: 'statuses',
    refs: [
      ['hifi', screen('3j'), '3j'],
      ['missing', '#M8 .win', 'M8'],
    ],
  },
  { name: 'states', refs: [['system', option('7b'), '7b']] },
  { name: 'dialogs', refs: [['system', option('7c'), '7c']] },
]

const types = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
}

function serveDesign() {
  const server = createHttpServer((request, response) => {
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

async function launch() {
  try {
    return await chromium.launch({ channel: 'chrome' })
  } catch {
    return chromium.launch()
  }
}

async function settle(page) {
  await page.evaluate(() => document.fonts.ready)
  await page.waitForTimeout(400)
}

async function shoot(page, selector, file) {
  const target = page.locator(selector).first()
  await target.scrollIntoViewIfNeeded()
  await target.screenshot({ path: join(out, file), animations: 'disabled' })
  return file
}

async function referenceShots(browser, designUrl, theme) {
  const shots = {}
  const page = await browser.newPage({ viewport })
  for (const [key, path] of Object.entries(pages)) {
    await page.goto(`${designUrl}/${encodeURI(path)}`, { waitUntil: 'networkidle' })
    if (key === 'missing' && theme === 'dark') {
      await page.evaluate(() => document.body.classList.add('theme-dark'))
    }
    await settle(page)
    if (key === 'system') {
      shots.sheet = await shoot(
        page,
        option(theme === 'dark' ? '7e' : '7d'),
        `ref-${theme}-sheet.png`,
      )
    }
    for (const extension of extensions) {
      for (const [source, selector, id] of extension.refs) {
        if (source !== key) continue
        const file = `ref-${theme}-${id}.png`
        shots[id] ??= await shoot(page, selector, file)
      }
    }
  }
  await page.close()
  return shots
}

async function sheetShots(browser, sheetUrl, theme, problems) {
  const page = await browser.newPage({ viewport })
  const foreign = []
  page.on('request', (request) => {
    if (!request.url().startsWith(sheetUrl.origin)) foreign.push(request.url())
  })
  page.on('console', (message) => {
    if (message.type() === 'error') problems.push(`${theme}: console error: ${message.text()}`)
  })
  page.on('pageerror', (error) => problems.push(`${theme}: page error: ${String(error)}`))
  await page.goto(`${sheetUrl.href}?theme=${theme}`, { waitUntil: 'networkidle' })
  await settle(page)
  const shots = {
    sheet: await shoot(
      page,
      theme === 'dark' ? '#sheet-7e' : '#sheet-7d',
      `ours-${theme}-sheet.png`,
    ),
  }
  for (const extension of extensions) {
    shots[extension.name] = await shoot(
      page,
      `[data-capture="${extension.name}"]`,
      `ours-${theme}-${extension.name}.png`,
    )
  }
  const results = await runChecks(page, theme)
  const opener = page.locator('[data-dialog-open]')
  await opener.click()
  const dialog = page.getByRole('dialog')
  const focusedInside = await dialog.evaluate((element) => element.contains(document.activeElement))
  results.push(`${focusedInside ? 'PASS' : 'FAIL'} ${theme}: dialog receives focus on open`)
  const controls = dialog.locator('button, input:not(:disabled)')
  const first = controls.first()
  await controls.last().focus()
  await page.keyboard.press('Tab')
  const wrapped = await first.evaluate((element) => element === document.activeElement)
  results.push(`${wrapped ? 'PASS' : 'FAIL'} ${theme}: Tab wraps from last dialog control to first`)
  await page.keyboard.press('Escape')
  const closed = (await dialog.count()) === 0
  const restored = await opener.evaluate((element) => element === document.activeElement)
  results.push(
    `${closed && restored ? 'PASS' : 'FAIL'} ${theme}: Escape closes dialog and restores opener focus`,
  )
  if (foreign.length)
    problems.push(`${theme}: requests outside the dev server: ${foreign.join(', ')}`)
  await page.close()
  return { shots, results }
}

async function pair(browser, left, right, title, file) {
  const page = await browser.newPage({ viewport: { width: 2900, height: 900 } })
  const image = (name) =>
    `data:image/png;base64,${readFileSync(join(out, name)).toString('base64')}`
  await page.setContent(`<body style="margin:0;padding:20px;background:#fff;font:13px system-ui">
    <p style="margin:0 0 12px">${title} · <b>visual review pending</b></p>
    <div style="display:flex;gap:20px;align-items:flex-start">
      <figure style="margin:0"><figcaption>handoff</figcaption><img src="${image(left)}"></figure>
      <figure style="margin:0"><figcaption>Ema (S17a)</figcaption><img src="${image(right)}"></figure>
    </div></body>`)
  await page.waitForLoadState('load')
  await page.screenshot({ path: join(out, file), fullPage: true })
  await page.close()
  return file
}

const design = await serveDesign()
const vite = await createViteServer({
  root: frontendRoot,
  logLevel: 'error',
  server: { host: '127.0.0.1', port: 5197, strictPort: false },
})
await vite.listen()
const sheetUrl = new URL('dev/sheet.html', vite.resolvedUrls.local[0])
const browser = await launch()
const problems = []
const report = []
const pairs = []

try {
  for (const theme of ['light', 'dark']) {
    const refs = await referenceShots(browser, design.url, theme)
    const { shots, results } = await sheetShots(browser, sheetUrl, theme, problems)
    report.push(...results)
    const sheetId = theme === 'dark' ? '7e' : '7d'
    pairs.push(
      await pair(
        browser,
        refs.sheet,
        shots.sheet,
        `${sheetId} component sheet (${theme})`,
        `pair-${theme}-sheet.png`,
      ),
    )
    for (const extension of extensions) {
      for (const [, , id] of extension.refs) {
        const label = `${extension.name} ← ${id} (${theme}${theme === 'dark' && !id.startsWith('M') ? '; the handoff draws this screen in light only' : ''})`
        pairs.push(
          await pair(
            browser,
            refs[id],
            shots[extension.name],
            label,
            `pair-${theme}-${extension.name}-${id}.png`,
          ),
        )
      }
    }
  }
} finally {
  await browser.close()
  await vite.close()
  design.server.close()
}

const failed = report.filter((line) => line.startsWith('FAIL'))
const passed = report.filter((line) => line.startsWith('PASS'))
const lines = [
  'S17a visual acceptance — visual review pending (the coordinator compares the pairs).',
  `viewport ${String(viewport.width)}×${String(viewport.height)}, handoff ${handoff}`,
  `summary: ${String(passed.length)} PASS, ${String(failed.length + problems.length)} FAIL, ${String(pairs.length)} pairs`,
  '',
  ...report,
  ...problems.map((problem) => `FAIL ${problem}`),
  '',
  `pairs: ${String(pairs.length)} in ${out}`,
  ...pairs.map((file) => `  ${file}`),
]
writeFileSync(join(out, 'checks.txt'), `${lines.join('\n')}\n`)
writeFileSync(
  join(out, 'index.html'),
  `<!doctype html><meta charset="utf-8"><title>S17a pairs</title><body style="font:13px system-ui">
  <h1>S17a — visual review pending</h1><pre>${lines.join('\n')}</pre>
  ${pairs.map((file) => `<p>${file}</p><img src="${file}" style="max-width:100%">`).join('\n')}</body>`,
)
console.log(lines.join('\n'))
process.exitCode = failed.length || problems.length ? 1 : 0
