// Local acceptance: the real CLIENT-A1 dossier through the audit UI and API.
// Never print client names, values, or document text. The seven .doc files use Word during intake.
import { execFileSync, spawn } from 'node:child_process'
import { mkdirSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { homedir, tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const reference = process.env.EMA_REFERENCE
if (!reference) throw new Error('EMA_REFERENCE is required')
const root = fileURLToPath(new URL('../..', import.meta.url))
const received = join(reference, 'audit/cases/audit-case-a/received')
const files = readdirSync(received).map((name) => join(received, name))
const outFlag = process.argv.indexOf('--out')
const artifacts = process.env.EMA_ARTIFACTS ?? join(homedir(), 'Code/projects/ema/artifacts')
const out =
  outFlag > 0 ? resolve(process.argv[outFlag + 1]) : join(artifacts, 's17b-audit-work/golden')
mkdirSync(out, { recursive: true })
const workspace =
  process.env.EMA_GOLDEN_WORKSPACE ?? mkdtempSync(join(tmpdir(), 'golden-s17b-audit-'))
const env = { ...process.env, EMA_WORKSPACE: workspace }
const results = []
const check = (ok, label) => {
  results.push(`${ok ? 'PASS' : 'FAIL'} ${label}`)
  if (!ok) throw new Error(`FAIL ${label}`)
}
let server
let browser
let step = 0
const shot = async (page, name) => {
  step += 1
  await page.screenshot({ path: join(out, `${String(step).padStart(2, '0')}-${name}.png`) })
}

function serve() {
  return new Promise((done, fail) => {
    const child = spawn('uv', ['run', 'ema', 'serve', '--port', '0'], { cwd: root, env })
    let buffer = ''
    child.stdout.on('data', (chunk) => {
      buffer += String(chunk)
      const match = /Open (http:\/\/127\.0\.0\.1:\d+\/app\/#code=\S+)/.exec(buffer)
      if (match) done({ child, url: match[1] })
    })
    child.on('exit', (code) => fail(new Error(`ema serve exited ${String(code)}`)))
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

async function waitRun(page, job, stage) {
  const until = Date.now() + 600_000
  while (Date.now() < until) {
    const status = (await api(page, 'GET', `/jobs/${job}/status`)).body
    const run = [...status.runs].reverse().find((item) => item.stage === stage)
    if (run && ['ready', 'failed', 'cancelled'].includes(run.state)) return run
    await new Promise((done) => setTimeout(done, 1500))
  }
  throw new Error(`stage ${stage} did not finish within ten minutes`)
}

try {
  check(files.length === 27, 'CLIENT-A1 dossier has 27 files')
  execFileSync('npm', ['run', 'build', '--prefix', 'frontend'], { cwd: root, stdio: 'ignore' })
  server = await serve()
  browser = await chromium.launch()
  const context = await browser.newContext({ viewport: { width: 1400, height: 900 } })
  const page = await context.newPage()
  await page.goto(server.url)
  await page.waitForFunction(() => Boolean(localStorage.getItem('ema.csrf')))
  let job
  if (process.env.EMA_GOLDEN_WORKSPACE) {
    const jobs = (await api(page, 'GET', '/jobs')).body
    job = jobs.find((item) => item.type === 'audit')?.id
    check(Boolean(job), 'reused audit workspace has a job')
    await page.goto(new URL(`/app/audit/${job}/revizuire`, server.url).href)
  } else {
    const client = await api(page, 'POST', '/clients', { name: 'CLIENT-A1 golden' })
    check(client.status === 201, 'client created in the temporary workspace')
    const created = await api(page, 'POST', '/jobs', {
      type: 'audit',
      client: client.body.id,
      year: 2026,
    })
    check(created.status === 200, 'audit job created in the temporary workspace')
    job = created.body.id
    await page.goto(new URL(`/app/audit/${job}/documente`, server.url).href)
    await page.getByRole('button', { name: 'Adaugă documente' }).first().click()
    await page.getByRole('dialog').locator('input[type=file]').setInputFiles(files)
    await page.getByRole('dialog').getByRole('button', { name: 'Adaugă documente' }).click()
    await page.waitForFunction(
      () => {
        const dialog = document.querySelector('[role="dialog"]')
        if (!dialog) return true
        const button = [...dialog.querySelectorAll('button')].find((item) =>
          item.textContent?.includes('Adaugă documente'),
        )
        return button && !button.disabled && dialog.querySelectorAll('.ema-failure').length > 0
      },
      null,
      { timeout: 180_000 },
    )
    if (await page.getByRole('dialog').count()) {
      const failed = await page.getByRole('dialog').locator('.ema-failure').count()
      const first = await page.getByRole('dialog').locator('.ema-failure').first().innerText()
      throw new Error(`upload rejected ${String(failed)} files: ${first.replaceAll('\n', ' ')}`)
    }
    const uploaded = (await api(page, 'GET', `/jobs/${job}/audit/documents`)).body
    check(uploaded.files.length === 27, 'all dossier files uploaded through the UI')
    await shot(page, 'documents-uploaded')

    await page.getByRole('button', { name: 'Citeşte dosarul' }).click()
    const intake = await waitRun(page, job, 'intake')
    check(intake.state === 'ready', `audit intake completed (${intake.state})`)
    await page.reload()
    const documents = (await api(page, 'GET', `/jobs/${job}/audit/documents`)).body
    check(
      JSON.stringify(documents.missing) === JSON.stringify([1, 3, 6, 10]),
      'checklist gaps match the delivered CLIENT-A1 expectation',
    )
    check(
      documents.files.length === 27 && documents.files.every((file) => Boolean(file.status)),
      'every dossier file has a visible status',
    )
    await shot(page, 'documents-read')

    await page.getByRole('button', { name: 'Extrage datele' }).click()
    const read = await waitRun(page, job, 'read')
    check(read.state === 'ready', 'audit data extraction completed')
    process.stdout.write('WORD_SLOT_RELEASED\n')
    const currentDocuments = (await api(page, 'GET', `/jobs/${job}/audit/documents`)).body
    check(
      currentDocuments.files.some((file) => file.status === 'read'),
      'read-stage document statuses are current',
    )
    await page.getByRole('tab', { name: /Revizuire/ }).click()
  }
  const fields = (await api(page, 'GET', `/jobs/${job}/fields`)).body.filter((field) =>
    field.key.startsWith('audit.'),
  )
  check(fields.length > 0, 'audit fields are listed by chapter for review')
  await page.locator('.audit-review-group').first().waitFor()
  await shot(page, 'review')

  const accepting = page.waitForResponse(
    (response) => response.url().includes('/decide') && response.request().method() === 'POST',
  )
  await page
    .locator('.ema-review-row')
    .first()
    .getByRole('button', { name: 'Acceptă', exact: true })
    .click()
  check((await accepting).status() === 200, 'one field accepted through the review row')
  const afterAcceptance = (await api(page, 'GET', `/jobs/${job}/fields`)).body
  const editable = afterAcceptance.find(
    (item) =>
      item.value_type === 'text' &&
      item.presence === 'found' &&
      item.review === 'pending' &&
      item.evidence?.length,
  )
  check(Boolean(editable), 'a sourced text field is available for correction')
  await page.goto(new URL(`/app/audit/${job}/revizuire?camp=${editable.id}`, server.url).href)
  const correct = page.locator('.ema-review-row').filter({ hasText: editable.label }).first()
  await correct.getByRole('button', { name: 'Scrie altă valoare' }).waitFor()
  await correct.getByRole('button', { name: 'Scrie altă valoare' }).click()
  const editor = page.locator('.value-editor').first()
  await editor.getByRole('textbox').fill('Valoare verificată')
  const correcting = page.waitForResponse((response) =>
    response.url().endsWith(`/fields/${editable.id}/decide`),
  )
  await editor.getByRole('button', { name: 'Salvează' }).click()
  check(
    (await correcting).status() === 200,
    'one sourced text field corrected through the review row',
  )
  await page.getByRole('tab', { name: 'Jurnal' }).click()
  await page.getByText('scris de tine').first().waitFor()
  check(
    (await page.getByText('acceptat', { exact: true }).count()) > 0,
    'acceptance and correction are in the journal',
  )
  await shot(page, 'journal')

  await page.getByRole('tab', { name: /Structura raportului/ }).click()
  const outline = (await api(page, 'GET', `/jobs/${job}/audit/outline`)).body
  const visitSection = outline.nodes.find((node) => node.id === 'ch3.flux')
  check(Boolean(visitSection), 'the visit-dependent report section is present')
  const section = page.locator('.audit-section-row').filter({ hasText: visitSection.title }).first()
  await section.getByRole('button', { name: 'Mai târziu' }).click()
  await section.getByRole('combobox').selectOption('visit')
  const marking = page.waitForResponse((response) => response.url().endsWith('/sections/ch3.flux'))
  await section.getByRole('button', { name: 'Salvează' }).click()
  check((await marking).status() === 200, 'visit-dependent section marked later in the UI')
  await page.getByText('mai târziu · vizită').first().waitFor()
  await shot(page, 'structure')
  writeFileSync(join(out, 'result.txt'), `${results.join('\n')}\n`)
  for (const item of results) process.stdout.write(`${item}\n`)
} catch (error) {
  writeFileSync(join(out, 'result.txt'), `${results.join('\n')}\nFAIL golden journey\n`)
  process.stderr.write(
    `FAIL golden journey: ${error instanceof Error ? error.message.split('\n')[0] : 'unknown error'}\n`,
  )
  process.exitCode = 1
} finally {
  if (browser) await browser.close()
  if (server) server.child.kill('SIGTERM')
  if (process.env.EMA_KEEP_GOLDEN_WORKSPACE === '1' || process.env.EMA_GOLDEN_WORKSPACE)
    process.stderr.write(`workspace: ${workspace}\n`)
  else rmSync(workspace, { recursive: true, force: true })
}
