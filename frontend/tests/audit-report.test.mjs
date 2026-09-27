import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'
import {
  CHAPTERS,
  auditChecks,
  canGenerateFinal,
  countRo,
  draftSummary,
  fieldsLine,
  markerLabels,
  pageIndex,
  tocItems,
  unitLine,
} from '../src/audit/report.ts'
import { CHECKS, REPORT, SECTIONS, SUMMARY } from './fixtures/audit-report/default.mjs'

test('CUPRINS: her seven chapters before a render, the rendered ones after', () => {
  const idle = { running: false, done: 0, total: 0 }
  assert.deepEqual(
    tocItems(null, idle).map((item) => [item.number, item.state]),
    CHAPTERS.map((item) => [item.number, 'todo']),
  )
  assert.equal(CHAPTERS[3].title, 'Analiza consumurilor energetice')
  const done = tocItems(SUMMARY, idle)
  assert.equal(done.length, 6)
  assert.deepEqual(done[3], {
    number: 4,
    title: SUMMARY.chapters[3].title,
    page: 3,
    state: 'done',
  })
  const writing = tocItems(SUMMARY, { running: true, done: 3, total: 7 })
  assert.deepEqual(
    writing.map((item) => item.state),
    ['done', 'done', 'done', 'working', 'todo', 'todo'],
  )
})

test('the draft summary is shown only when that draft finished', () => {
  assert.equal(draftSummary(REPORT), SUMMARY)
  assert.equal(draftSummary({ ...REPORT, draft: { ...REPORT.draft, state: 'failed' } }), null)
  assert.equal(draftSummary(undefined), null)
})

test('page map: a TOC page becomes a preview index inside the document', () => {
  assert.equal(pageIndex(3, 10), 2)
  assert.equal(pageIndex(40, 10), 9)
  assert.equal(pageIndex(null, 10), null)
  assert.equal(pageIndex(3, 0), null)
})

test('markers are grouped by section; the lines of the panel', () => {
  assert.deepEqual(markerLabels(SUMMARY.markers), [
    'Concluziile privind analiza consumului',
    'Măsuri de creştere a eficienţei energetice',
  ])
  assert.equal(unitLine(SUMMARY.unit_plan), '2 secţii · 4 tablouri măsurate · 3 măsuri')
  assert.equal(
    unitLine({ ...SUMMARY.unit_plan, processes: 1, processes_source: 'default' }),
    '1 secţie · 4 tablouri măsurate · 3 măsuri · număr de secţii presupus',
  )
  assert.equal(
    unitLine({ ...SUMMARY.unit_plan, processes: 20, measured_panels: 1, measures: 101 }),
    '20 de secţii · 1 tablou măsurat · 101 măsuri',
  )
  assert.equal(fieldsLine(SUMMARY), '2 câmpuri încă în revizuire')
  assert.equal(fieldsLine({ ...SUMMARY, fields_confirmed: 119 }), '1 câmp încă în revizuire')
  assert.equal(fieldsLine({ ...SUMMARY, fields_confirmed: 120 }), '5 câmpuri introduse manual')
  assert.equal(
    fieldsLine({ ...SUMMARY, fields_confirmed: 120, fields_manual: 0 }),
    'toate au sursă în documente',
  )
})

test('Romanian counts: singular, plural, and „de” from 20 within each hundred', () => {
  const counts = [1, 2, 19, 20, 100, 101, 119, 120].map((n) => countRo(n, 'câmp', 'câmpuri'))
  assert.deepEqual(counts, [
    '1 câmp',
    '2 câmpuri',
    '19 câmpuri',
    '20 de câmpuri',
    '100 de câmpuri',
    '101 câmpuri',
    '119 câmpuri',
    '120 de câmpuri',
  ])
})

test('a stale final counts as an old draft and never blocks the next final', () => {
  const stale = {
    readiness: {
      draft_ok: true,
      final_ok: false,
      blocking: [{ code: 'final_stale', message: 'Versiunea finală nu mai corespunde datelor.' }],
    },
    readiness_hash: 'h',
  }
  assert.equal(canGenerateFinal(stale), true)
  assert.equal(canGenerateFinal(CHECKS), false)
  assert.deepEqual(auditChecks(stale, undefined, false)[1], {
    label: 'Nicio ciornă nu e veche',
    tone: 'err',
    detail: '1',
  })
  const ai = {
    ...stale,
    readiness: { ...stale.readiness, blocking: [{ code: 'ai_wording', message: 'AI' }] },
  }
  assert.equal(auditChecks(ai, undefined, false)[3].tone, 'err')
})

test('the five checks derive from the blocking codes', () => {
  assert.deepEqual(auditChecks(CHECKS, SECTIONS, true), [
    { label: 'Toate secţiunile au răspuns', tone: 'err', detail: '2/4' },
    { label: 'Nicio ciornă nu e veche', tone: 'ok', detail: 'la zi' },
    { label: 'Toate diferenţele dintre surse sunt decise', tone: 'err', detail: '1' },
    { label: 'Valorile citite de pe fotografii sunt confirmate', tone: 'err', detail: '1' },
    { label: 'Toate textele sunt scrise', tone: 'err', detail: '1' },
  ])
  const ready = { readiness: { draft_ok: true, final_ok: true, blocking: [] }, readiness_hash: 'h' }
  assert.deepEqual(
    auditChecks(ready, undefined, false).map((check) => [check.tone, check.detail]),
    [
      ['ok', 'la zi'],
      ['ok', 'la zi'],
      ['ok', 'la zi'],
      ['ok', 'la zi'],
    ],
  )
})

function files(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    return statSync(path).isDirectory() ? files(path) : [path]
  })
}

test('pdf.js has one importer, the preview has one loader, and nothing logs', () => {
  const sources = files('src').filter((path) => /\.(ts|tsx)$/.test(path))
  const importers = (pattern) =>
    sources.filter((path) => pattern.test(readFileSync(path, 'utf8'))).sort()
  assert.deepEqual(importers(/from 'pdfjs-dist(\/[^']*)?'/), ['src/api/pdf.ts'])
  assert.deepEqual(importers(/from '[./]*\/api\/pdf\.ts'/), ['src/screens/audit/PdfPages.tsx'])
  const owned = [
    'src/api/audit-report.ts',
    'src/api/audit-report-types.ts',
    'src/api/pdf.ts',
    'src/audit/report.ts',
    'src/screens/audit/ReportScreen.tsx',
    'src/screens/audit/ReportToc.tsx',
    'src/screens/audit/PdfPages.tsx',
    'src/screens/audit/ReportPanel.tsx',
    'src/screens/audit/AuditExportScreen.tsx',
  ]
  for (const path of owned) assert.doesNotMatch(readFileSync(path, 'utf8'), /\bconsole\./, path)
})
