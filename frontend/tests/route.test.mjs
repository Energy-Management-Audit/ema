import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { TABS, href, jobHref, parseRoute } from '../src/app/route.ts'

test('every href lives under /app/', () => {
  assert.equal(href({ name: 'home' }), '/app/')
  for (const tab of TABS) {
    const link = jobHref('job-piee-1', tab)
    assert.ok(link.startsWith('/app/'), link)
    assert.equal(link, `/app/piee/job-piee-1/${tab}`)
  }
  assert.equal(jobHref('job-piee-1', 'date', 'f-annual'), '/app/piee/job-piee-1/date?camp=f-annual')
})

test('routes parse back, with the camp query', () => {
  assert.deepEqual(parseRoute('/app/'), { name: 'home' })
  assert.deepEqual(parseRoute('/app'), { name: 'home' })
  assert.deepEqual(parseRoute('/app/piee/j/masuri'), {
    name: 'job',
    jobId: 'j',
    tab: 'masuri',
    field: null,
  })
  assert.deepEqual(parseRoute('/app/piee/j/date', '?camp=f-1'), {
    name: 'job',
    jobId: 'j',
    tab: 'date',
    field: 'f-1',
  })
  assert.deepEqual(parseRoute('/app/piee/j/other'), { name: 'unknown' })
})

test('no Vite proxy key starts with /app', () => {
  const config = readFileSync(new URL('../vite.config.ts', import.meta.url), 'utf8')
  const keys = [...config.matchAll(/'(\/[^']*)':\s*\{\s*target/g)].map((match) => match[1])
  assert.ok(keys.length >= 8)
  assert.deepEqual(
    keys.filter((key) => key.startsWith('/app')),
    [],
  )
})
