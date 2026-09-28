// Synthetic audit job for the Raport Word (3d) and Predare (7a) harnesses. No client data.

import { CLIENTS, JOBS, baseRoutes } from '../base.mjs'

export const JOB = 'job-audit-1'
export const J = `/jobs/${JOB}`
const at = '2026-09-27T08:00:00+00:00'
export const job = JOBS.find((item) => item.id === JOB)

/** A small valid PDF with `pages` blank A4 pages, each carrying its number as text. */
export function pdf(pages = 3) {
  const objects = ['<< /Type /Catalog /Pages 2 0 R >>']
  const kids = Array.from({ length: pages }, (_, index) => `${String(3 + index * 2)} 0 R`)
  objects.push(`<< /Type /Pages /Kids [${kids.join(' ')}] /Count ${String(pages)} >>`)
  const font = 3 + pages * 2
  for (let index = 0; index < pages; index++) {
    const content = `BT /F1 18 Tf 72 760 Td (Pagina ${String(index + 1)}) Tj ET`
    objects.push(
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents ${String(4 + index * 2)} 0 R /Resources << /Font << /F1 ${String(font)} 0 R >> >> >>`,
    )
    objects.push(`<< /Length ${String(content.length)} >>\nstream\n${content}\nendstream`)
  }
  objects.push('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
  let body = '%PDF-1.4\n'
  const offsets = []
  objects.forEach((object, index) => {
    offsets.push(body.length)
    body += `${String(index + 1)} 0 obj\n${object}\nendobj\n`
  })
  const xref = body.length
  body += `xref\n0 ${String(objects.length + 1)}\n0000000000 65535 f \n`
  for (const offset of offsets) body += `${String(offset).padStart(10, '0')} 00000 n \n`
  body += `trailer\n<< /Size ${String(objects.length + 1)} /Root 1 0 R >>\nstartxref\n${String(xref)}\n%%EOF\n`
  return body
}

export const SUMMARY = {
  kind: 'draft',
  chapters: [
    { number: 1, title: 'Descrierea şi scopul auditului', section_id: 'ch1', page: 1 },
    { number: 2, title: 'Descrierea şi istoricul societăţii', section_id: 'ch2', page: 2 },
    { number: 3, title: 'Descrierea situaţiei existente', section_id: 'ch3', page: 2 },
    {
      number: 4,
      title: 'Analiza modului în care se realizează consumurile energetice pe platforma societății',
      section_id: 'ch4',
      page: 3,
    },
    { number: 5, title: 'Măsuri de creştere a eficienţei energetice', section_id: 'ch6', page: 3 },
    { number: 6, title: 'Surse de finanţare', section_id: 'ch7', page: 3 },
  ],
  tables: 9,
  charts: 0,
  markers: [
    { section_id: 'ch4.concluzii', label: 'Concluziile privind analiza consumului' },
    { section_id: 'ch4.concluzii', label: 'Concluziile privind analiza consumului' },
    { section_id: 'ch6', label: 'Măsuri de creştere a eficienţei energetice' },
  ],
  fields_total: 120,
  fields_confirmed: 118,
  fields_manual: 5,
  unit_plan: {
    client_name: 'Doi Industrie SRL',
    processes: 2,
    processes_source: 'fisa',
    carriers: ['electricity', 'gas'],
    measured_panels: 4,
    thermal_measurements: true,
    equipment_tables: 1,
    measures: 3,
  },
  pdf: true,
  toc_pages_set: true,
  dropped: ['ch4.bilant_real'],
  failures: [],
  charts_skipped: [],
}

export const DRAFT_RUN = {
  run_id: 'run-draft-1',
  state: 'ready',
  ended_at: at,
  current: true,
  summary: SUMMARY,
  docx_output_id: 'out-draft-docx',
  pdf_output_id: 'out-draft-pdf',
}

export const REPORT = { draft: DRAFT_RUN, final: null, word: true }

const output = (id, name, kind, runId, stage, size) => ({
  id,
  version: 1,
  kind,
  media_type: name.endsWith('.pdf')
    ? 'application/pdf'
    : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  size_bytes: size,
  edited_externally: false,
  name,
  created_at: at,
  run_id: runId,
  stage,
})

export const OUTPUTS = [
  output('out-draft-pdf', 'Audit-ciorna.pdf', 'draft', 'run-draft-1', 'audit_render', 812_000),
  output('out-draft-docx', 'Audit-ciorna.docx', 'draft', 'run-draft-1', 'audit_render', 2_400_000),
]

export const FINAL_OUTPUTS = [
  ...OUTPUTS,
  output('out-final-pdf', 'Audit-final.pdf', 'draft', 'run-final-1', 'audit_final', 815_000),
  output('out-final-docx', 'Audit-final.docx', 'final', 'run-final-1', 'audit_final', 2_410_000),
]

export const FINAL_RUN = {
  run_id: 'run-final-1',
  state: 'ready',
  ended_at: at,
  current: true,
  summary: { ...SUMMARY, kind: 'final', markers: [] },
  docx_output_id: 'out-final-docx',
  pdf_output_id: 'out-final-pdf',
}

export const CHECKS = {
  readiness: {
    draft_ok: true,
    final_ok: false,
    blocking: [
      { code: 'section_open', field_id: null, message: 'Date generale: Completați şi confirmați' },
      { code: 'section_open', field_id: null, message: 'Istoric: Completați şi confirmați' },
      { code: 'conflict', field_id: 'f-1', message: 'Consum gaz 2025: două valori' },
      { code: 'narrative_missing', field_id: 'f-2', message: 'Textul lipseşte: Concluzii' },
      { code: 'reading_unconfirmed', field_id: 'f-3', message: 'Confirmaţi valoarea' },
    ],
    warnings: [],
    next: [],
  },
  readiness_hash: 'hash-open',
}

export const READY_CHECKS = {
  readiness: { draft_ok: true, final_ok: true, blocking: [], warnings: [], next: [] },
  readiness_hash: 'hash-ready',
}

export const SECTIONS = [
  { section_id: 'ch1', status: 'done', stale: false },
  { section_id: 'ch2.date_generale', status: 'drafted', stale: false },
  { section_id: 'ch2.istorie', status: 'missing', stale: false },
  { section_id: 'ch4.bilant_real', status: 'n/a', stale: false },
]

export const VISIT = {
  panels: [
    {
      id: 'tg-1',
      label: 'TG 1',
      photos: [{ sha: 'aaa', slot: 'visit/meter/TG 1/a.jpg', name: 'a.jpg' }],
    },
  ],
  thermal: [],
}

/** A server-sent stream for the job's events, as `GET /jobs/{id}/events` writes it. */
export function eventStream(events) {
  return events
    .map((event, index) => {
      const seq = index + 1
      const data = { seq, job_id: JOB, at, payload: {}, ...event }
      return `id: ${String(seq)}\nevent: ${data.type}\ndata: ${JSON.stringify(data)}\n\n`
    })
    .join('')
}

// The harness sets the theme through GET /settings, so that read is not overridden here.
const shared = Object.fromEntries(
  Object.entries(baseRoutes).filter(([key]) => key !== 'GET /settings'),
)

export const reportRoutes = {
  ...shared,
  [`GET ${J}`]: { status: 200, body: job },
  'GET /clients/client-doi': { status: 200, body: CLIENTS[1] },
  [`GET ${J}/status`]: {
    status: 200,
    body: { id: JOB, type: 'audit', state: 'open', revision: 1, runs: [] },
  },
  [`GET ${J}/export/checks`]: { status: 200, body: CHECKS },
  [`GET ${J}/outputs`]: { status: 200, body: OUTPUTS },
  [`GET ${J}/log`]: { status: 200, body: [] },
  [`GET ${J}/fields`]: { status: 200, body: [] },
  [`GET ${J}/audit/report`]: { status: 200, body: REPORT },
  [`GET ${J}/approvals`]: { status: 200, body: [] },
  [`GET ${J}/sections`]: { status: 200, body: SECTIONS },
  [`GET ${J}/visit`]: { status: 200, body: VISIT },
  [`GET ${J}/outputs/out-draft-pdf`]: { status: 200, contentType: 'application/pdf', body: pdf(3) },
  [`GET ${J}/outputs/out-final-pdf`]: { status: 200, contentType: 'application/pdf', body: pdf(4) },
  [`GET ${J}/events`]: { status: 200, contentType: 'text/event-stream', body: eventStream([]) },
}

/** Every section answered, as a ready job has them. */
export const ANSWERED = SECTIONS.map((item) => ({
  ...item,
  status: item.status === 'n/a' ? 'n/a' : 'done',
}))
