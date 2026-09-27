// D9.2 golden (local only): the audit report journey on CLIENT-A1's received dossier through the built
// app, the real API and Word for Mac. Client values stay in the workspace and the artifacts
// folder; the script prints only pass/fail lines, counts and file names.
//
//   EMA_REFERENCE=… EMA_ARTIFACTS=… node frontend/scripts/golden-s17b-audit-report.mjs [--out <dir>]
//   exit 0 pass · 1 fail · 2 Blocked: word_unavailable
//
// Round-1 revision: a real audit's final is refused for markers no field or n/a can clear
// (cover, ch. 1, ch. 7), so the journey ends at Predare X1 with that refusal, not at X4.

import { execFileSync, spawn } from 'node:child_process'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { homedir, tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'
import { countRo } from '../src/audit/report.ts'

const reference = process.env.EMA_REFERENCE
if (!reference) throw new Error('EMA_REFERENCE is not set.')
const artifacts = process.env.EMA_ARTIFACTS ?? join(homedir(), 'Code/projects/ema/artifacts')
const outFlag = process.argv.indexOf('--out')
const out =
  outFlag > 0 ? resolve(process.argv[outFlag + 1]) : join(artifacts, 's17b-audit-report', 'golden')
mkdirSync(out, { recursive: true })
const repo = fileURLToPath(new URL('../..', import.meta.url))
const workspace = mkdtempSync(join(tmpdir(), 'ema-golden-audit-'))
const scratch = mkdtempSync(join(tmpdir(), 'ema-golden-audit-scratch-'))
const golden = 'tests.golden.test_s17b_audit_render'
const report = []
const check = (ok, label) => {
  report.push(`${ok ? 'PASS' : 'FAIL'} ${label}`)
  if (!ok) throw new Error(`FAIL ${label}`)
}
let step = 0
const shot = async (page, name) => {
  step += 1
  await page.screenshot({ path: join(out, `ui-${String(step).padStart(2, '0')}-${name}.png`) })
}
const python = (args, env) =>
  JSON.parse(
    execFileSync('uv', ['run', 'python', '-m', golden, ...args], {
      cwd: repo,
      env,
      encoding: 'utf8',
      maxBuffer: 1 << 24,
    })
      .trim()
      .split('\n')
      .at(-1),
  )

function serve(env) {
  return new Promise((done, fail) => {
    const child = spawn('uv', ['run', 'ema', 'serve', '--port', '0'], { cwd: repo, env })
    let buffer = ''
    child.stdout.on('data', (chunk) => {
      buffer += String(chunk)
      const match = /Open ((http:\/\/127\.0\.0\.1:\d+)\/app\/#code=\S+)/.exec(buffer)
      if (match) done({ child, url: match[1], origin: match[2] })
    })
    child.on('exit', (code) => {
      fail(new Error(`ema serve exited ${String(code)}`))
    })
  })
}

async function api(page, path) {
  return page.evaluate(async (target) => (await fetch(target)).json(), path)
}

let server = null
let browser = null
try {
  execFileSync('npm', ['run', 'build', '--prefix', 'frontend'], { cwd: repo, stdio: 'ignore' })
  const base = { ...process.env, EMA_WORKSPACE: workspace }
  const seeded = python(['seed', workspace, scratch], base)
  const job = seeded.job
  check(Boolean(job), 'seeded: CLIENT-A1 intake + read, two replayed drafts, three measures')
  const env = { ...base, ...seeded.env }
  server = await serve(env)
  browser = await chromium.launch()
  const context = await browser.newContext({
    viewport: { width: 1400, height: 900 },
    acceptDownloads: true,
  })
  const page = await context.newPage()
  const consoleLines = []
  const offOrigin = []
  page.on('console', (message) => {
    if (!message.text().startsWith('Failed to load resource')) consoleLines.push(message.text())
  })
  page.on('request', (request) => {
    if (new URL(request.url()).origin !== server.origin) offOrigin.push(request.url())
  })
  await page.goto(server.url)
  await page.waitForLoadState('networkidle')
  await page.goto(`${server.origin}/app/audit/${job}/raport`)
  await page.getByRole('button', { name: 'Generează ciorna' }).waitFor()
  await page.getByText('Previzualizarea apare după prima ciornă.').waitFor()
  await shot(page, 'raport-empty')

  await page.getByRole('button', { name: 'Generează ciorna' }).click()
  const progress = page.getByTestId('report-progress')
  await progress.waitFor()
  await progress.getByText(/ capitole$/).waitFor()
  await shot(page, 'raport-running')
  const failure = page.getByRole('alert')
  await Promise.race([
    page.getByRole('button', { name: 'Generează ciorna' }).waitFor({ timeout: 900_000 }),
    failure.first().waitFor({ timeout: 900_000 }),
  ])
  if ((await failure.count()) > 0) {
    await shot(page, 'raport-failed')
    const text = await failure.first().innerText()
    if (/Word/.test(text)) {
      report.push('Blocked: word_unavailable')
      process.exitCode = 2
    }
    throw new Error(`render: ${text.split('\n')[0]}`)
  }
  const view = await api(page, `/jobs/${job}/audit/report`)
  check(view.draft?.state === 'ready' && view.word, 'the draft is ready and Word is present')
  check(
    view.draft.summary.pdf && view.draft.summary.toc_pages_set,
    'Word set the TOC page numbers and made the PDF',
  )
  await page.getByTestId('pdf-pages').waitFor({ timeout: 60_000 })
  const pdfPath = join(scratch, 'draft.pdf')
  const bytes = await page.evaluate(
    async (target) => Array.from(new Uint8Array(await (await fetch(target)).arrayBuffer())),
    `/jobs/${job}/outputs/${view.draft.pdf_output_id}`,
  )
  writeFileSync(pdfPath, Buffer.from(bytes))
  const pages = Number(
    execFileSync(
      'uv',
      [
        'run',
        'python',
        '-c',
        'import sys, pypdfium2; print(len(pypdfium2.PdfDocument(sys.argv[1])))',
        pdfPath,
      ],
      { cwd: repo, encoding: 'utf8' },
    ).trim(),
  )
  const shown = Number(await page.getByTestId('pdf-pages').getAttribute('data-pages'))
  check(pages > 0 && shown === pages, `the preview shows every page of the PDF (${String(pages)})`)
  await page.locator('.report-page__canvas').first().waitFor()
  await shot(page, 'raport-preview')
  const chapters = view.draft.summary.chapters
  const target = chapters.find((item) => item.section_id === 'ch4') ?? chapters.at(-1)
  await page
    .getByTestId('report-toc')
    .getByRole('button', { name: new RegExp(`^${String(target.number)} · `) })
    .click()
  const index = Math.min(target.page, pages) - 1
  const jumped = await page
    .waitForFunction(
      (at) => {
        const frame = document.querySelectorAll('[data-testid="pdf-page"]')[at]
        const box = frame.getBoundingClientRect()
        return box.top >= 0 && box.top < 400
      },
      index,
      { timeout: 10_000 },
    )
    .then(
      () => true,
      () => false,
    )
  await shot(page, 'raport-jump')
  check(jumped, `CUPRINS jumps to chapter ${String(target.number)}'s page (${String(target.page)})`)
  const markers = view.draft.summary.markers.length
  if (markers > 0) {
    await page
      .getByTestId('report-markers')
      .getByText(countRo(markers, 'câmp rămas gol', 'câmpuri rămase goale'))
      .waitFor()
  }
  check(true, `the panel lists ${String(markers)} empty fields`)

  // Predare: final readiness through the use cases, then the final is refused for markers.
  const prepared = python(['final', workspace, scratch, job], env)
  check(
    prepared.final_ok === true,
    'final_ok through the use cases (drafted -> done, the rest n/a)',
  )
  await page.goto(`${server.origin}/app/audit/${job}/predare`)
  const final = page.getByRole('button', { name: 'Generează versiunea finală' })
  await final.waitFor()
  await page.waitForFunction(
    () =>
      [...document.querySelectorAll('button')].some(
        (button) => button.textContent === 'Generează versiunea finală' && !button.disabled,
      ),
    null,
    { timeout: 30_000 },
  )
  await shot(page, 'predare-x1')
  await final.click()
  const refused = page
    .getByRole('alert')
    .filter({ hasText: 'Raportul final are câmpuri necompletate.' })
  await refused.waitFor({ timeout: 900_000 })
  await shot(page, 'predare-refused')
  const finals = (await api(page, `/jobs/${job}/audit/report`)).final
  check(
    finals?.state === 'failed' && (await refused.count()) === 1,
    'the final is refused for markers, by its title (the sections are in the Python golden)',
  )
  await page.reload()
  await refused.waitFor()
  check(
    (await page.getByRole('button', { name: 'Aprobă şi exportă' }).count()) === 0,
    'a reload keeps X1 with the refusal; nothing to approve',
  )
  check(offOrigin.length === 0, 'no request outside the app origin')
  check(consoleLines.length === 0, 'no console message from the app')
} catch (error) {
  if (process.exitCode !== 2) {
    process.exitCode = 1
    report.push(`FAIL ${error instanceof Error ? error.message.split('\n')[0] : 'error'}`)
  }
} finally {
  console.log(['S17b audit-report golden:', ...report, `screenshots: ${out}`].join('\n'))
  await browser?.close()
  if (server) {
    const stopped = new Promise((done) => {
      server.child.once('exit', done)
    })
    server.child.kill('SIGTERM')
    await stopped
  }
  rmSync(workspace, { recursive: true, force: true, maxRetries: 5, retryDelay: 500 })
  rmSync(scratch, { recursive: true, force: true, maxRetries: 5, retryDelay: 500 })
}
