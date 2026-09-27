// D11 behaviour harness: the built app served by Vite, every API call answered from a route table
// (the synthetic fixture unless a test overrides it). An unmatched API request or any console
// message fails the test.

import { mkdtempSync, rmSync } from 'node:fs'
import { createServer } from 'node:net'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'
import { build, preview } from 'vite'
import { defaultRoutes } from '../fixtures/piee/default.mjs'

const root = fileURLToPath(new URL('../..', import.meta.url))
const API =
  /^\/(session|health|jobs|clients|evidence|reporting|settings|backups|audit|openapi\.json)(\/|$|\?)/

let built = null

/** One production build per test process: no dev client and no React dev notice in the console. */
function buildOnce() {
  built ??= (async () => {
    const outDir = mkdtempSync(join(tmpdir(), 'ema-e2e-'))
    process.on('exit', () => {
      rmSync(outDir, { recursive: true, force: true })
    })
    await build({ root, logLevel: 'silent', build: { outDir, emptyOutDir: true } })
    return outDir
  })()
  return built
}

function freePort() {
  return new Promise((resolve, reject) => {
    const server = createServer()
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address()
      server.close(() => {
        resolve(port)
      })
    })
  })
}

function parseBody(request) {
  const raw = request.postData()
  if (raw === null) return null
  const type = request.headers()['content-type'] ?? ''
  if (type.includes('application/json')) return JSON.parse(raw)
  return raw
}

export async function startHarness({
  theme = 'light',
  viewport = { width: 1400, height: 900 },
  routes = {},
  path,
} = {}) {
  const outDir = await buildOnce()
  const server = await preview({
    root,
    logLevel: 'silent',
    build: { outDir },
    preview: { host: '127.0.0.1', port: await freePort(), strictPort: true, proxy: {} },
  })
  const origin = server.resolvedUrls.local[0].replace(/\/$/, '')
  const table = {
    ...defaultRoutes,
    'GET /settings': {
      ...defaultRoutes['GET /settings'],
      body: { ...defaultRoutes['GET /settings'].body, theme },
    },
    ...routes,
  }
  const requests = []
  const failures = []
  // Chromium reports every non-2xx response as a console line of its own. For an API problem this
  // harness served on purpose that line is the browser, not the app, so it alone is not a failure.
  const served = new Set()
  const consoleFailure = (message) => {
    const text = message.text()
    const status = /^Failed to load resource: the server responded with a status of (\d+)/.exec(
      text,
    )
    if (status && served.has(`${message.location().url} ${status[1]}`)) return
    failures.push(`console ${message.type()}: ${text}`)
  }
  const browser = await chromium.launch()
  const context = await browser.newContext({ viewport, acceptDownloads: true })
  const page = await context.newPage()
  context.on('page', (opened) => {
    if (opened !== page) opened.on('console', consoleFailure)
  })
  page.on('console', consoleFailure)
  page.on('pageerror', (error) => {
    failures.push(`page error: ${error.message}`)
  })
  await context.route('**/*', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (url.origin !== origin) {
      failures.push(`request outside the app origin: ${url.origin}`)
      return route.abort()
    }
    if (!API.test(url.pathname)) return route.continue()
    const target = url.pathname + url.search
    requests.push({
      method: request.method(),
      path: target,
      body: parseBody(request),
      headers: request.headers(),
      resourceType: request.resourceType(),
    })
    const key = `${request.method()} ${target}`
    let answer = table[key]
    if (typeof answer === 'function') answer = await answer(request)
    if (!answer) {
      failures.push(`unmatched API request: ${key}`)
      return route.fulfill({
        status: 599,
        contentType: 'application/problem+json',
        body: JSON.stringify({ type: 'urn:ema:error:unmatched', title: 'unmatched', status: 599 }),
      })
    }
    const { status = 200, body = null, contentType } = answer
    if (status >= 400) served.add(`${request.url()} ${String(status)}`)
    const text = typeof body === 'string' ? body : JSON.stringify(body)
    const type =
      contentType ??
      (typeof body === 'string'
        ? 'text/plain'
        : status >= 400
          ? 'application/problem+json'
          : 'application/json')
    return route.fulfill({ status, contentType: type, body: text })
  })
  await page.goto(`${origin}${path ?? '/app/'}#code=test-code`)

  return {
    page,
    origin,
    requests,
    failures,
    setRoute(key, response) {
      table[key] = response
    },
    async close() {
      await browser.close()
      await new Promise((resolve) => {
        server.httpServer.close(resolve)
      })
      if (failures.length > 0) throw new Error(`harness failures:\n${failures.join('\n')}`)
    },
  }
}

/** A problem+json answer, as the API writes it. */
export function problem(code, status, title) {
  return { status, body: { type: `urn:ema:error:${code}`, title, status } }
}
