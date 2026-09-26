// S17b visual acceptance (D10): our PIEE states from the synthetic fixture through the e2e
// harness, the handoff and Claude-drawn references, paired side by side at 1400×900 in both themes
// and repeated at 1280×800 for review, plus the deterministic layout checks. Output outside git.
//
//   EMA_REFERENCE=… EMA_ARTIFACTS=… npm run capture:s17b --prefix frontend [-- --out <dir>]

import {
  createReadStream,
  existsSync,
  mkdirSync,
  readFileSync,
  statSync,
  writeFileSync,
} from 'node:fs'
import { createServer } from 'node:http'
import { homedir } from 'node:os'
import { extname, join, normalize, resolve, sep } from 'node:path'
import { chromium } from 'playwright'
import {
  FINAL_OUTPUTS,
  JOB,
  OUTPUTS,
  READY_CHECKS,
  eventStream,
} from '../tests/fixtures/piee/default.mjs'
import { startHarness } from '../tests/e2e/harness.mjs'
import { focusCheck, fontChecks, layoutChecks, line, paperChecks } from './s17b-checks.mjs'

const reference = process.env.EMA_REFERENCE
if (!reference)
  throw new Error('EMA_REFERENCE is not set; the handoff lives in $EMA_REFERENCE/design.')
const designRoot = resolve(reference, 'design')
const artifacts = process.env.EMA_ARTIFACTS ?? join(homedir(), 'Code/projects/ema/artifacts')
const outFlag = process.argv.indexOf('--out')
const out = outFlag > 0 ? resolve(process.argv[outFlag + 1]) : join(artifacts, 's17b-piee')
mkdirSync(out, { recursive: true })

const J = `/jobs/${JOB}`
const pages = {
  hifi: 'handoff-2026-09-21/EMA Hi-Fi.dc.html',
  dark: 'handoff-2026-09-21/EMA Dark.dc.html',
  system: 'handoff-2026-09-21/EMA Design System.dc.html',
  missing: 'missing-screens-2026-09-24/EMA Missing Screens.html',
}
const screen = (id) => `[id="${id}"] [data-screen-label]`
const option = (id) => `[id="${id}"] > div:nth-of-type(2)`
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
const editedOutputs = OUTPUTS.map((item) =>
  item.id === 'out-draft-1' ? { ...item, edited_externally: true } : item,
)
const exportRoutes = {
  [`GET ${J}/outputs`]: { status: 200, body: FINAL_OUTPUTS },
  [`GET ${J}/export/checks`]: { status: 200, body: READY_CHECKS },
}

// Each pair: the reference per theme (null where the handoff draws only one theme) and our state.
const PAIRS = [
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
  {
    id: '7c-DG1',
    refs: { light: ['system', option('7c')] },
    path: `/app/piee/${JOB}/date`,
    activity: true,
    routes: { [`GET ${J}/outputs`]: { status: 200, body: editedOutputs } },
    async act(page) {
      await page.getByRole('button', { name: 'Generează programul' }).click()
      await page.getByRole('dialog').waitFor()
    },
  },
]

const types = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
}
function serveDesign() {
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

async function settle(page) {
  await page.waitForLoadState('networkidle')
  await page.evaluate(() => document.fonts.ready)
  await page.waitForTimeout(300)
}

async function referenceShots(browser, designUrl) {
  const shots = {}
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } })
  for (const theme of ['light', 'dark']) {
    for (const pair of PAIRS) {
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

async function ourShots(theme, viewport, report) {
  const shots = {}
  const suffix = viewport.width === 1400 ? '' : `-${String(viewport.width)}`
  for (const pair of PAIRS) {
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
      if (pair.act) await pair.act(page)
      await settle(page)
      const file = `ours-${theme}-${pair.id}${suffix}.png`
      await page.screenshot({ path: join(out, file), animations: 'disabled' })
      shots[`${theme}-${pair.id}`] = file
      report.push(...(await layoutChecks(page, label, pair, viewport)))
      report.push(...(await fontChecks(page, label)))
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

async function pair(browser, left, right, title, file) {
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

const design = await serveDesign()
const browser = await chromium.launch()
const report = []
const pairs = []
try {
  const refs = await referenceShots(browser, design.url)
  for (const theme of ['light', 'dark']) {
    const ours = await ourShots(theme, { width: 1400, height: 900 }, report)
    for (const item of PAIRS) {
      pairs.push(
        await pair(
          browser,
          refs[`${theme}-${item.id}`],
          ours[`${theme}-${item.id}`],
          `${item.id} (${theme})`,
          `pair-${theme}-${item.id}.png`,
        ),
      )
    }
    await ourShots(theme, { width: 1280, height: 800 }, report)
  }
} finally {
  await browser.close()
  design.server.close()
}

const failed = report.filter((item) => item.startsWith('FAIL'))
const lines = [
  'S17b visual acceptance — visual review pending (the coordinator compares the pairs).',
  `summary: ${String(report.length - failed.length)} PASS, ${String(failed.length)} FAIL, ${String(pairs.length)} pairs`,
  '',
  ...report,
  '',
  `pairs in ${out}`,
  ...pairs.map((file) => `  ${file}`),
]
writeFileSync(join(out, 'checks.txt'), `${lines.join('\n')}\n`)
writeFileSync(
  join(out, 'index.html'),
  `<!doctype html><meta charset="utf-8"><title>S17b pairs</title><body style="font:13px system-ui">
  <h1>S17b — visual review pending</h1><pre>${lines.join('\n')}</pre>
  ${pairs.map((file) => `<p>${file}</p><img src="${file}" style="max-width:100%">`).join('\n')}</body>`,
)
console.log(lines.join('\n'))
process.exitCode = failed.length ? 1 : 0
