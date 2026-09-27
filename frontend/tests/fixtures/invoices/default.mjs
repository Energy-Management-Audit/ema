import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { baseRoutes, CLIENTS, JOBS } from '../base.mjs'

const schemas = JSON.parse(
  readFileSync(new URL('../../../../openapi/ema.v1.json', import.meta.url), 'utf8'),
).components.schemas

function wireDecimal(model, property, value) {
  const field = schemas[model].properties[property]
  const variants = field.anyOf ?? [field]
  assert.deepEqual(
    variants.map((item) => item.type).filter((type) => type !== 'null'),
    ['string'],
    `${model}.${property} must travel as a JSON string`,
  )
  return String(value)
}

export const JOB = 'job-invoices-1'
export const CLIENT = 'client-exemplu'
export const J = `/jobs/${JOB}`
export const job = JOBS.find((item) => item.id === JOB)
export const client = CLIENTS.find((item) => item.id === CLIENT)
export const at = '2026-09-27T08:00:00+00:00'

export const ready = {
  id: 'run-invoices-1',
  stage: 'invoices',
  state: 'ready',
  publication: 'current',
}
export const status = { id: JOB, type: 'invoices', state: 'ready', revision: 1, runs: [ready] }
export const checks = {
  readiness: {
    draft_ok: true,
    final_ok: false,
    blocking: [{ code: 'not_ready', message: 'Clientul lotului nu este confirmat.' }],
    next: ['Clientul lotului nu este confirmat.'],
  },
  readiness_hash: 'hash-invoices',
}
export const identity = {
  batch_id: 'run-invoices-1',
  candidate: { client_id: CLIENT, cui: 'RO1234567', pod: 'POD0001' },
  confirmed: false,
  evidence_ids: ['invoice-evidence-1'],
  revision: 1,
  name: 'Exemplu Energie SA',
  reasons: { printed: 11, pods: ['POD0001'], other_client: 0 },
  pod_fill: [{ pod: 'POD0001', files: ['fara-pod.pdf'], source_count: 10 }],
  memory: [],
  files_total: 13,
  client_cui: 'RO1234567',
}

function row(month, amount, outlier = null) {
  const date = `2026-${month}-28`
  return {
    id: `row-${month}`,
    month: `2026-${month}`,
    consumption_kwh: wireDecimal('InvoiceRow', 'consumption_kwh', amount),
    source_evidence_ids: [],
    anomalies: [],
    file_name: `${month}.pdf`,
    slot: `invoices/${month.padStart(4, '0')}`,
    supplier: 'Furnizor Exemplu',
    invoice_number: `F-${month}`,
    invoice_date: date,
    status: 'exportable',
    issues: [],
    price_lei_kwh: wireDecimal('InvoiceRow', 'price_lei_kwh', '0.8000'),
    value_lei: wireDecimal('InvoiceRow', 'value_lei', amount * 0.8),
    sources: { active_energy: { page: 1, snippet: `Consum: ${String(amount)} kWh` } },
    outlier,
  }
}
export const rows = Array.from({ length: 12 }, (_, index) => String(index + 1).padStart(2, '0'))
  .filter((month) => month !== '02')
  .map((month) =>
    row(
      month,
      month === '10' ? 2000 : 1000,
      month === '10'
        ? {
            ratio: wireDecimal('InvoiceOutlier', 'ratio', 2),
            neighbours_mean_kwh: wireDecimal('InvoiceOutlier', 'neighbours_mean_kwh', 1000),
          }
        : null,
    ),
  )
export const batch = {
  batch_id: identity.batch_id,
  identity,
  rows,
  missing_months: ['2026-02'],
  files: [
    {
      slot: 'invoices/0013',
      file_name: 'bad.pdf',
      status: 'failed',
      reason:
        'Fişierul e o scanare fără text şi la 110 dpi. Sub 200 dpi nu pot extrage cifrele cu încredere.',
    },
    {
      slot: 'invoices/0014',
      file_name: 'gas.pdf',
      status: 'unsupported',
      reason: 'Doar facturi electrice.',
    },
  ],
  totals: {
    months: 11,
    consumption_kwh: wireDecimal('InvoiceTotals', 'consumption_kwh', 12000),
    value_lei: wireDecimal('InvoiceTotals', 'value_lei', 9600),
    price_avg_lei_kwh: wireDecimal('InvoiceTotals', 'price_avg_lei_kwh', '0.8'),
  },
  year: 2026,
  read_ended_at: at,
}
export const acceptedIdentity = { ...identity, confirmed: true }
export const acceptedBatch = { ...batch, identity: acceptedIdentity }
export const confirmedChecks = {
  readiness: { draft_ok: true, final_ok: true, blocking: [], next: [] },
  readiness_hash: 'hash-confirmed',
}
export const decision = {
  id: 'decision-client-1',
  at,
  actor: 'user',
  field_id: 'field-client',
  on_revision: 1,
  action: 'accept',
  before: {},
  after: { key: 'invoice.batch_client' },
  undone_by: null,
}
export const output = {
  id: 'output-excel-1',
  version: 1,
  kind: 'final',
  media_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  size_bytes: 23456,
  edited_externally: false,
  name: 'Facturi.xlsx',
  created_at: at,
  run_id: 'run-workbook-1',
  stage: 'invoices_workbook',
}
export const pageSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="550" height="200" viewBox="0 0 550 200"><rect width="550" height="200" fill="#fffdf6"/><text x="32" y="48" font-size="17" fill="#777064">FACTURĂ FISCALĂ · EXTRAS</text><text x="32" y="112" font-size="28" fill="#252219">Consum activ</text><rect x="225" y="77" width="201" height="50" rx="4" fill="#faedc8" stroke="#ac6b0c" stroke-width="2"/><text x="239" y="112" font-size="29" font-weight="700" fill="#252219">2000 kWh</text></svg>`
export const invoiceRoutes = {
  ...baseRoutes,
  [`GET ${J}`]: { status: 200, body: { ...job, state: 'ready' } },
  [`GET /clients/${CLIENT}`]: { status: 200, body: client },
  [`GET ${J}/status`]: { status: 200, body: status },
  [`GET ${J}/export/checks`]: { status: 200, body: checks },
  [`GET ${J}/slots`]: {
    status: 200,
    body: rows.map((item) => item.slot).concat('invoices/0013', 'invoices/0014'),
  },
  [`GET ${J}/fields`]: { status: 200, body: [{ id: 'field-client', key: 'invoice.batch_client' }] },
  [`GET ${J}/log`]: { status: 200, body: [] },
  [`GET ${J}/outputs`]: { status: 200, body: [] },
  [`GET ${J}/invoices/identity`]: { status: 200, body: identity },
  [`GET ${J}/invoices`]: { status: 200, body: batch },
  'GET /evidence/invoice-evidence-1/quote': {
    status: 200,
    body: {
      id: 'invoice-evidence-1',
      provenance: 'document',
      file_sha: 'sha-identity',
      locator: { kind: 'pdf_text', page: 1 },
      method: 'invoice',
      retrieved_at: at,
      quote: 'Client: Exemplu Energie SA',
      highlight: 'page',
    },
  },
  [`GET ${J}/slots/${rows[0].slot}/versions`]: {
    status: 200,
    body: [
      {
        job_id: JOB,
        slot: rows[0].slot,
        version: 1,
        file_sha: 'sha-identity',
        origin: rows[0].file_name,
        converted_from: null,
        slot_revision: 2,
      },
    ],
  },
  ...Object.fromEntries(
    rows.slice(1).map((item) => [
      `GET ${J}/slots/${item.slot}/versions`,
      {
        status: 200,
        body: [
          {
            job_id: JOB,
            slot: item.slot,
            version: 1,
            file_sha: item.id,
            origin: item.file_name,
            converted_from: null,
            slot_revision: 2,
          },
        ],
      },
    ]),
  ),
  [`GET ${J}/slots/invoices/0013/versions`]: {
    status: 200,
    body: [
      {
        job_id: JOB,
        slot: 'invoices/0013',
        version: 1,
        file_sha: 'sha-bad',
        origin: 'bad.pdf',
        converted_from: null,
        slot_revision: 2,
      },
    ],
  },
  [`GET ${J}/slots/invoices/0014/versions`]: {
    status: 200,
    body: [
      {
        job_id: JOB,
        slot: 'invoices/0014',
        version: 1,
        file_sha: 'sha-gas',
        origin: 'gas.pdf',
        converted_from: null,
        slot_revision: 2,
      },
    ],
  },
  [`GET ${J}/invoices/page.png?slot=invoices%2F0010&page=1&crop=active_energy`]: {
    status: 200,
    body: pageSvg,
    contentType: 'image/svg+xml',
  },
  [`GET ${J}/invoices/file?slot=invoices%2F0010`]: {
    status: 200,
    body: '%PDF synthetic',
    contentType: 'application/pdf',
  },
}
