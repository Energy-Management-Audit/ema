// D12 golden (local only): the PIEE journey on CLIENT-P1's received files through the built app, the
// real API and Word for Mac. Client values stay in the workspace and the artifacts folder; the
// script prints only pass/fail lines, file names and hashes.
//
//   EMA_REFERENCE=… EMA_ARTIFACTS=… npm run golden:s17b --prefix frontend [-- --out <dir>]
//   exit 0 pass · 1 fail · 2 Blocked: word_unavailable

import { execFileSync, spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs'
import { homedir, tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'
import { MONTHS } from '../src/piee/labels.ts'

const reference = process.env.EMA_REFERENCE
if (!reference) throw new Error('EMA_REFERENCE is not set.')
const artifacts = process.env.EMA_ARTIFACTS ?? join(homedir(), 'Code/projects/ema/artifacts')
const outFlag = process.argv.indexOf('--out')
const out =
  outFlag > 0 ? resolve(process.argv[outFlag + 1]) : join(artifacts, 's17b-piee', 'golden')
mkdirSync(out, { recursive: true })
const repo = fileURLToPath(new URL('../..', import.meta.url))
const received = join(reference, 'piee/cases/piee-case-a/received')
const pick = (pattern) =>
  join(
    received,
    readdirSync(received).find((name) => pattern.test(name)),
  )
const programs = join(reference, 'piee/finished-programs')
const workspace = mkdtempSync(join(tmpdir(), 'ema-golden-s17b-'))
const env = {
  ...process.env,
  EMA_WORKSPACE: workspace,
  EMA_PIEE_BASE_DOCUMENT: join(
    programs,
    readdirSync(programs).find((name) => name.includes('MODEL_2026')),
  ),
  EMA_PIEE_BASE_DIRECTORY: join(artifacts, 's8', 'base'),
}
const report = []
const check = (ok, label) => {
  report.push(`${ok ? 'PASS' : 'FAIL'} ${label}`)
  if (!ok) throw new Error(`FAIL ${label}`)
}
let step = 0
const shot = async (page, name) => {
  step += 1
  await page.screenshot({ path: join(out, `${String(step).padStart(2, '0')}-${name}.png`) })
}

/** The ways a document may print a value: 1.234,56 · 1234,56 · 1 234,56, 0–3 decimals. */
function spellings(value) {
  const result = new Set()
  for (const places of [0, 1, 2, 3]) {
    const [integer, fraction] = Number(value).toFixed(places).split('.')
    for (const group of ['', '.', ' ', ' ']) {
      const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, group)
      result.add(fraction ? `${grouped},${fraction}` : grouped)
    }
  }
  return [...result].filter((item) => item.replace(/\D/g, '').length >= 4)
}

function holds(part, value) {
  return (
    spellings(value).some((text) => part.text.includes(`>${text}<`)) ||
    part.text.includes(`<c:v>${String(Number(value))}</c:v>`)
  )
}

function docxParts(path) {
  return execFileSync('unzip', ['-Z1', path], { encoding: 'utf8' })
    .split('\n')
    .filter((name) => name.startsWith('word/') && name.endsWith('.xml'))
    .map((name) => ({
      name,
      text: execFileSync('unzip', ['-p', path, name], { encoding: 'utf8', maxBuffer: 1 << 28 }),
    }))
}

function serve() {
  return new Promise((done, fail) => {
    const child = spawn('uv', ['run', 'ema', 'serve', '--port', '0'], { cwd: repo, env })
    let buffer = ''
    child.stdout.on('data', (chunk) => {
      buffer += String(chunk)
      const match = /Open (http:\/\/127\.0\.0\.1:\d+\/app\/#code=\S+)/.exec(buffer)
      if (match) done({ child, url: match[1] })
    })
    child.on('exit', (code) => {
      fail(new Error(`ema serve exited ${String(code)}`))
    })
  })
}

async function api(page, method, path, body) {
  return page.evaluate(
    async ([verb, target, payload]) => {
      const response = await fetch(target, {
        method: verb,
        headers: {
          'content-type': 'application/json',
          'x-ema-csrf': localStorage.getItem('ema.csrf') ?? '',
        },
        body: payload === null ? undefined : JSON.stringify(payload),
      })
      return { status: response.status, body: await response.json() }
    },
    [method, path, body ?? null],
  )
}

async function recordOpens(page) {
  await page.evaluate(() => {
    const original = window.open.bind(window)
    window.__opened = []
    window.open = (url, ...rest) => {
      window.__opened.push(String(url))
      return original(url, ...rest)
    }
  })
}

let server = null
let browser = null
try {
  execFileSync('npm', ['run', 'build', '--prefix', 'frontend'], { cwd: repo, stdio: 'ignore' })
  const seeded = JSON.parse(
    execFileSync(
      'uv',
      [
        'run',
        'ema',
        'piee',
        'generate',
        '--client',
        'CLIENT-P1',
        '--year',
        '2025',
        '--anexa',
        pick(/^Anexa.*\.xlsx$/),
        '--necesar',
        pick(/^Necesar.*\.xls$/),
        '--prelucrare',
        pick(/Prelucrare.*\.xls/),
      ],
      { cwd: repo, env, encoding: 'utf8' },
    ),
  )
  const job = seeded.job
  check(Boolean(job), 'seeded: import + first draft through the CLI')
  server = await serve()
  browser = await chromium.launch()
  const context = await browser.newContext({
    viewport: { width: 1400, height: 900 },
    acceptDownloads: true,
  })
  const page = await context.newPage()
  const consoleLines = []
  page.on('console', (message) => {
    if (!message.text().startsWith('Failed to load resource')) consoleLines.push(message.text())
  })
  await page.goto(server.url)
  await page.getByRole('heading', { name: 'Bine ai revenit.' }).waitFor()
  await page.goto(new URL(`/app/piee/${job}/date`, server.url).toString())
  await page.waitForURL(`**/app/piee/${job}/date`)
  await page.getByTestId('carrier-table-electricity_grid').waitFor()
  await shot(page, 'date')

  // Every conflict decided in the UI, the first alternative of each.
  for (let guard = 0; guard < 60; guard += 1) {
    const row = page.locator('[data-testid^="conflict-row-"]').first()
    if ((await row.count()) === 0) break
    const id = await row.getAttribute('data-testid')
    await row.locator('.ema-source-btn').click()
    await row
      .getByRole('button', { name: /^Foloseşte / })
      .first()
      .click()
    await page.getByTestId(id).waitFor({ state: 'detached' })
  }
  check(
    (await page.locator('[data-testid^="conflict-row-"]').count()) === 0,
    'every conflict decided in the UI',
  )
  await shot(page, 'conflicts-decided')

  // A data-year month corrected in the carrier table (C2), then the months/annual cross-check (C1).
  const grid = page.getByTestId('carrier-table-electricity_grid')
  const cellButton = grid.getByRole('button', { name: /^Corectează .+ · \S+ 2025$/ }).first()
  const monthName = (await cellButton.getAttribute('aria-label')).split(' · ')[1].split(' ')[0]
  const monthIndex = MONTHS.indexOf(monthName) + 1
  const fields = (await api(page, 'GET', `/jobs/${job}/fields`)).body
  const monthKey = `carrier.electricity_grid.2025.${String(monthIndex).padStart(2, '0')}`
  const month = fields.find((item) => item.key === monthKey)
  const annual = fields.find((item) => item.key === 'carrier.electricity_grid.2025')
  const old = String(month.value)
  const corrected = (Number(old) + 111.11).toFixed(2)
  await cellButton.click()
  await grid.getByRole('textbox').fill(corrected.replace('.', ','))
  const monthSaved = page.waitForResponse((item) =>
    item.url().endsWith(`/fields/${month.id}/decide`),
  )
  await grid.getByRole('button', { name: 'Salvează' }).click()
  check((await monthSaved).status() === 200, 'one data-year month corrected in the S3 table (C2)')
  const banner = page.getByTestId('months-annual-banner')
  await banner.waitFor({ timeout: 30_000 }).catch(() => undefined)
  check(
    (await banner.count()) === 1 &&
      (await banner.innerText()).includes('Suma lunilor nu se potriveşte cu totalul anual'),
    'the months no longer add up to the filed annual: M4 banner (C1)',
  )
  await shot(page, 'months-annual-banner')
  const annualCorrected = (Number(annual.value) + 111.11).toFixed(5)
  await banner.getByRole('button', { name: 'Corectează totalul anual' }).click()
  await banner.getByRole('textbox').fill(annualCorrected.replace('.', ','))
  const annualSaved = page.waitForResponse((item) =>
    item.url().endsWith(`/fields/${annual.id}/decide`),
  )
  await banner.getByRole('button', { name: 'Salvează' }).click()
  check((await annualSaved).status() === 200, 'the annual value corrected from the banner')
  await banner.waitFor({ state: 'detached', timeout: 30_000 })
  check(true, 'the banner clears once months and annual agree')
  await page.reload()
  await page.getByText('ciornă veche · datele s-au schimbat').waitFor()
  await page.getByRole('button', { name: 'Generează programul' }).click()
  await page.getByTestId('run-panel').waitFor()
  await shot(page, 'generating')
  await page.getByTestId('run-panel').waitFor({ state: 'detached', timeout: 600_000 })
  await page.getByRole('tab', { name: /Documente/ }).click()
  const drafts = (await api(page, 'GET', `/jobs/${job}/outputs`)).body.filter(
    (item) => item.kind === 'draft' && item.name.endsWith('.docx'),
  )
  const draft = drafts.at(-1)
  check(drafts.length === 2, 'a second draft, no second import')
  const downloading = page.waitForEvent('download')
  await page.getByTestId(`output-row-${draft.id}`).getByRole('button', { name: 'Descarcă' }).click()
  const draftPath = join(workspace, 'draft.docx')
  await (await downloading).saveAs(draftPath)
  await shot(page, 'documents')
  const holding = docxParts(draftPath).filter((part) => holds(part, corrected))
  check(
    holding.length > 0,
    `the corrected month is in the draft (${holding.map((part) => part.name).join(', ')})`,
  )
  check(
    holding.every((part) => !holds(part, old)),
    'the old month value is gone from those parts',
  )

  // Predare: the Word package, the same-run PDF, the approval.
  await page.goto(page.url().replace(/\/documente$/, '/predare'))
  const packager = page.getByRole('button', { name: 'Generează pachetul' })
  await packager.waitFor()
  await page.waitForLoadState('networkidle')
  const enabled = await page
    .waitForFunction(
      () =>
        [...document.querySelectorAll('button')].some(
          (button) => button.textContent === 'Generează pachetul' && !button.disabled,
        ),
      null,
      { timeout: 30_000 },
    )
    .then(
      () => true,
      () => false,
    )
  await shot(page, 'predare')
  check(enabled, 'final_ok after the decisions (Generează pachetul enabled)')
  await packager.click()
  const approve = page.getByRole('button', { name: 'Aprobă şi exportă' })
  const failure = page.locator('[role="alert"]')
  await Promise.race([
    approve.waitFor({ timeout: 900_000 }),
    failure.first().waitFor({ timeout: 900_000 }),
  ])
  if ((await approve.count()) === 0) {
    await shot(page, 'package-failed')
    const text = await failure.first().innerText()
    if (/Word/.test(text)) {
      report.push('Blocked: word_unavailable')
      process.exitCode = 2
    }
    throw new Error(`package: ${text.split('\n')[0]}`)
  }
  await shot(page, 'package')
  await page.goto(page.url().replace(/\/predare$/, '/date'))
  await page.getByTestId('carrier-table-electricity_grid').waitFor()
  await recordOpens(page)
  const pdfRequest = page.waitForRequest((request) =>
    /\/outputs\/[^/]+$/.test(new URL(request.url()).pathname),
  )
  await page.getByRole('button', { name: 'Previzualizare' }).click()
  const pdfPath = new URL((await pdfRequest).url()).pathname
  const finals = (await api(page, 'GET', `/jobs/${job}/outputs`)).body
  const final = finals.at(-1)
  const pdf = finals.find((item) => pdfPath.endsWith(`/${item.id}`))
  check(
    pdf?.media_type === 'application/pdf' && pdf.run_id === final.run_id,
    'Previzualizare opens the PDF of the final run',
  )
  await page.waitForFunction(() => window.__opened.length > 0)
  check(
    (await page.evaluate(() => window.__opened[0])).startsWith('blob:'),
    'the preview is a blob URL',
  )
  await page.goto(page.url().replace(/\/date$/, '/predare'))
  const response = page.waitForResponse((item) => item.url().endsWith(`/jobs/${job}/export`))
  await page.getByRole('button', { name: 'Aprobă şi exportă' }).click()
  check((await response).status() === 200, 'Aprobă şi exportă answers 200')
  await page.getByText('Copia finală e în dosarul de exporturi al lucrării.').waitFor()
  await shot(page, 'approved')
  const exported = readFileSync(join(workspace, 'exports', `${job}-${final.id}.docx`))
  const served = await page.evaluate(async (path) => {
    return Array.from(new Uint8Array(await (await fetch(path)).arrayBuffer()))
  }, `/jobs/${job}/outputs/${final.id}`)
  const hash = (bytes) => createHash('sha256').update(bytes).digest('hex')
  check(
    hash(exported) === hash(Buffer.from(served)),
    `the export equals the final output (sha256 ${hash(exported)})`,
  )
  await page.reload()
  await page.getByText(/^Aprobat /).waitFor()
  await shot(page, 'x4-after-reload')
  check(true, 'a reload shows X4')
  check(consoleLines.length === 0, 'no console message from the app')
} catch (error) {
  if (process.exitCode !== 2) {
    process.exitCode = 1
    report.push(`FAIL ${error instanceof Error ? error.message.split('\n')[0] : 'error'}`)
  }
} finally {
  console.log(['S17b golden:', ...report, `screenshots: ${out}`].join('\n'))
  await browser?.close()
  if (server) {
    const stopped = new Promise((done) => {
      server.child.once('exit', done)
    })
    server.child.kill('SIGTERM')
    await stopped
  }
  rmSync(workspace, { recursive: true, force: true, maxRetries: 5, retryDelay: 500 })
}
