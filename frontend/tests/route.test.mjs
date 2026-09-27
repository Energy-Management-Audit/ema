import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import {
  AUDIT_TABS,
  CLIENT_TABS,
  SETTINGS_GROUPS,
  TABS,
  auditHref,
  clientHref,
  href,
  invoicesHref,
  jobHref,
  jobPath,
  parseRoute,
} from '../src/app/route.ts'

test('every href lives under /app/', () => {
  assert.equal(href({ name: 'home' }), '/app/')
  for (const tab of TABS) {
    const link = jobHref('job-piee-1', tab)
    assert.ok(link.startsWith('/app/'), link)
    assert.equal(link, `/app/piee/job-piee-1/${tab}`)
  }
  assert.equal(jobHref('job-piee-1', 'date', 'f-annual'), '/app/piee/job-piee-1/date?camp=f-annual')
  assert.equal(auditHref('audit 1'), '/app/audit/audit%201/documente')
  assert.equal(
    auditHref('audit 1', 'masuratori', 'reading-1'),
    '/app/audit/audit%201/masuratori?camp=reading-1',
  )
  assert.equal(invoicesHref('invoice 1'), '/app/facturi/invoice%201')
  assert.equal(clientHref('client 1'), '/app/clienti/client%201/date')
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
  assert.deepEqual(parseRoute('/app/audit/a/masuratori', '?camp=f-2'), {
    name: 'audit',
    jobId: 'a',
    tab: 'masuratori',
    field: 'f-2',
  })
  for (const tab of AUDIT_TABS) {
    const route = { name: 'audit', jobId: 'audit 1', tab, field: null }
    assert.deepEqual(parseRoute(new URL(href(route), 'http://local').pathname), route)
  }
  for (const tab of CLIENT_TABS) {
    const route = { name: 'client', clientId: 'client 1', tab }
    assert.deepEqual(parseRoute(new URL(href(route), 'http://local').pathname), route)
  }
  for (const group of SETTINGS_GROUPS) {
    const route = { name: 'settings', group }
    assert.deepEqual(parseRoute(href(route)), route)
  }
  for (const route of [
    { name: 'clients' },
    { name: 'reporting' },
    { name: 'invoices', jobId: 'invoice 1' },
  ]) {
    assert.deepEqual(parseRoute(href(route)), route)
  }
  assert.deepEqual(parseRoute('/app/setari'), { name: 'settings', group: 'extragere' })
  assert.deepEqual(parseRoute('/app/clienti/client%201'), {
    name: 'client',
    clientId: 'client 1',
    tab: 'date',
  })
  assert.deepEqual(parseRoute('/app/other'), { name: 'unknown' })
  assert.equal(jobPath({ id: 'id', type: 'piee' }), '/app/piee/id/date')
  assert.equal(jobPath({ id: 'id', type: 'audit' }), '/app/audit/id/documente')
  assert.equal(jobPath({ id: 'id', type: 'invoices' }), '/app/facturi/id')
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

test('the app passes route parameters to each area screen', () => {
  const app = readFileSync(new URL('../src/app/App.tsx', import.meta.url), 'utf8')
  const audit = readFileSync(
    new URL('../src/screens/audit/AuditJobScreen.tsx', import.meta.url),
    'utf8',
  )
  assert.match(app, /<ClientScreen clientId=\{route\.clientId\} tab=\{route\.tab\} \/>/)
  assert.match(app, /<SettingsScreen group=\{route\.group\} \/>/)
  assert.match(app, /<InvoiceJobScreen jobId=\{route\.jobId\} \/>/)
  assert.match(
    app,
    /<AuditJobScreen jobId=\{route\.jobId\} tab=\{route\.tab\} field=\{route\.field\} \/>/,
  )
  assert.match(audit, /<ReportScreen jobId=\{jobId\} \/>/)
  assert.match(audit, /<AuditExportScreen jobId=\{jobId\} \/>/)
  assert.match(
    audit,
    /export type AuditJobScreenProps = \{ jobId: string; tab: AuditTab; field: string \| null \}/,
  )
})
