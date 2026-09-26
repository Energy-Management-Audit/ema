// Synthetic PIEE job for the e2e harness (D11). Invented company and figures; no client data.

import { ANNUAL, EVIDENCE, FIELDS, JOB } from './fields.mjs'

export { ANNUAL, EVIDENCE, FIELDS, JOB, REGISTRU, TERM_P2 } from './fields.mjs'

export const CLIENT = 'client-exemplu'
const at = '2026-09-25T08:00:00+00:00'
const J = `/jobs/${JOB}`

export const CHECKS = {
  readiness: {
    draft_ok: true,
    final_ok: false,
    blocking: [
      { code: 'conflict', field_id: 'f-annual', message: 'Conflict: Date anuale total tep' },
    ],
    warnings: [],
    next: ['Conflict: Date anuale total tep'],
  },
  readiness_hash: 'hash-1',
}

export const OUTPUTS = [
  {
    id: 'out-xlsx-1',
    version: 1,
    kind: 'draft',
    media_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    size_bytes: 98_304,
    edited_externally: false,
    name: 'Prelucrare-date.xlsx',
    created_at: at,
    run_id: 'run-gen-1',
    stage: 'piee_generate',
  },
  {
    id: 'out-draft-1',
    version: 2,
    kind: 'draft',
    media_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    size_bytes: 4_299_161,
    edited_externally: false,
    name: 'PIEE-draft.docx',
    created_at: at,
    run_id: 'run-gen-1',
    stage: 'piee_generate',
  },
]

/** The outputs after a piee_word run: xlsx, pdf and the final docx of `run-word-1`. */
export const FINAL_OUTPUTS = [
  ...OUTPUTS,
  {
    id: 'out-xlsx-2',
    version: 3,
    kind: 'draft',
    media_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    size_bytes: 98_304,
    edited_externally: false,
    name: 'Prelucrare-date.xlsx',
    created_at: at,
    run_id: 'run-word-1',
    stage: 'piee_word',
  },
  {
    id: 'out-pdf-1',
    version: 4,
    kind: 'draft',
    media_type: 'application/pdf',
    size_bytes: 1_887_436,
    edited_externally: false,
    name: 'PIEE-final.pdf',
    created_at: at,
    run_id: 'run-word-1',
    stage: 'piee_word',
  },
  {
    id: 'out-final-1',
    version: 5,
    kind: 'final',
    media_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    size_bytes: 4_311_040,
    edited_externally: false,
    name: 'PIEE-final.docx',
    created_at: at,
    run_id: 'run-word-1',
    stage: 'piee_word',
  },
]

export const READY_CHECKS = {
  readiness: { draft_ok: true, final_ok: true, blocking: [], warnings: [], next: [] },
  readiness_hash: 'hash-ready',
}

export const SUMMARY = {
  total_tep: { value: '22164.05', unit: 'tep', field_ids: ['f-annual'], missing: [] },
  annual_check: 'mismatch',
  savings_mwh: {
    value: '840',
    unit: 'MWh/an',
    field_ids: [
      'f-planned-1-saving',
      'f-planned-2-saving',
      'f-planned-3-saving',
      'f-planned-4-saving',
    ],
    missing: [],
  },
  investment_thousand_lei: {
    value: '660',
    unit: 'mii lei',
    field_ids: [
      'f-planned-1-investment',
      'f-planned-2-investment',
      'f-planned-3-investment',
      'f-planned-4-investment',
    ],
    missing: [],
  },
  measures_total: 7,
  measures_complete: 5,
  measures_without_term: 1,
}

export const LOG = [
  {
    id: 'd-1',
    at,
    actor: 'user',
    field_id: 'f-cui',
    target_kind: 'field',
    on_revision: 1,
    action: 'accept',
    before: { ...FIELDS.find((item) => item.id === 'f-cui') },
    after: { ...FIELDS.find((item) => item.id === 'f-cui'), review: 'accepted' },
    batch_id: null,
    undone_by: null,
  },
  {
    id: 'd-2',
    at,
    actor: 'user',
    field_id: 'f-planned-1-saving',
    target_kind: 'field',
    on_revision: 1,
    action: 'correct',
    before: {
      key: 'measure.planned.1.saving_mwh',
      label: 'x',
      value: '230',
      unit: 'MWh',
      value_type: 'number',
    },
    after: {
      key: 'measure.planned.1.saving_mwh',
      label: 'x',
      value: '238',
      unit: 'MWh',
      value_type: 'number',
    },
    batch_id: null,
    undone_by: 'd-3',
  },
  {
    id: 'd-3',
    at,
    actor: 'user',
    field_id: 'f-planned-1-saving',
    target_kind: 'field',
    on_revision: 2,
    action: 'undo',
    before: {
      key: 'measure.planned.1.saving_mwh',
      label: 'x',
      value: '238',
      unit: 'MWh',
      value_type: 'number',
    },
    after: {
      key: 'measure.planned.1.saving_mwh',
      label: 'x',
      value: '230',
      unit: 'MWh',
      value_type: 'number',
    },
    batch_id: null,
    undone_by: null,
  },
]

const job = { id: JOB, type: 'piee', client_slug: CLIENT, year: 2026, state: 'ready', revision: 7 }
const client = {
  id: CLIENT,
  name: 'Exemplu Energie SA',
  cui: 'RO1234567',
  caen: null,
  sites: [],
  contacts: [],
  revision: 1,
  anaf_refreshed_at: null,
}
const files = {
  anexa: { sha: 'sha-anexa', name: 'Anexa 2 si 3 consum 2025 - Exemplu.xlsx', size_bytes: 90_112 },
  questionnaire: {
    sha: 'sha-questionnaire',
    name: 'Necesar info 2025 - Exemplu.xls',
    size_bytes: 421_888,
  },
  prelucrare: {
    sha: 'sha-prelucrare',
    name: 'Exemplu - Prelucrare date 2023-2025.xlsx',
    size_bytes: 3_355_443,
  },
}

export const defaultRoutes = {
  'POST /session': { status: 200, body: { csrf: 'csrf-token' } },
  'GET /settings': {
    status: 200,
    body: {
      theme: 'light',
      default_provider: null,
      providers: {},
      extraction: { ocr: true, flag_uncertain: true, auto_accept_exact: false },
    },
  },
  'GET /jobs': { status: 200, body: [job] },
  'GET /clients': { status: 200, body: [client] },
  [`GET /clients/${CLIENT}`]: { status: 200, body: client },
  [`GET ${J}`]: { status: 200, body: job },
  [`GET ${J}/status`]: {
    status: 200,
    body: {
      id: JOB,
      type: 'piee',
      state: 'ready',
      revision: 7,
      runs: [
        {
          id: 'run-import-1',
          stage: 'piee_import',
          state: 'ready',
          publication: 'current',
          error: null,
        },
        {
          id: 'run-gen-1',
          stage: 'piee_generate',
          state: 'ready',
          publication: 'current',
          error: null,
        },
      ],
    },
  },
  [`GET ${J}/fields`]: { status: 200, body: FIELDS },
  [`GET ${J}/fields?status=missing`]: {
    status: 200,
    body: FIELDS.filter((item) => item.value === null || item.review === 'rejected'),
  },
  [`GET ${J}/conflicts`]: { status: 200, body: [ANNUAL] },
  [`GET ${J}/export/checks`]: { status: 200, body: CHECKS },
  [`GET ${J}/piee/summary`]: { status: 200, body: SUMMARY },
  [`GET ${J}/outputs`]: { status: 200, body: OUTPUTS },
  [`GET ${J}/approvals`]: { status: 200, body: [] },
  [`GET ${J}/log`]: { status: 200, body: LOG },
  [`GET ${J}/slots`]: { status: 200, body: ['anexa', 'prelucrare', 'questionnaire'] },
  [`GET ${J}/prelucrare`]: {
    status: 200,
    body: {
      input: { file_id: 'sha-prelucrare', years: [2023, 2024, 2025] },
      output: { id: 'out-xlsx-1', version: 1 },
      authority: 'input_for_covered_years',
    },
  },
  [`GET ${J}/outputs/out-draft-1`]: {
    status: 200,
    body: 'PK synthetic draft',
    contentType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  },
  [`GET ${J}/outputs/out-xlsx-1`]: {
    status: 200,
    body: 'PK synthetic workbook',
    contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  },
  [`GET ${J}/outputs/out-final-1`]: {
    status: 200,
    body: 'PK synthetic final',
    contentType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  },
  [`GET ${J}/outputs/out-pdf-1`]: {
    status: 200,
    body: '%PDF-1.4 synthetic',
    contentType: 'application/pdf',
  },
}
for (const [slot, file] of Object.entries(files)) {
  defaultRoutes[`GET ${J}/slots/${slot}/versions`] = {
    status: 200,
    body: [
      { job_id: JOB, slot, version: 1, file_sha: file.sha, origin: 'upload', converted_from: null },
    ],
  }
  defaultRoutes[`GET /clients/${CLIENT}/files/${file.sha}/versions`] = {
    status: 200,
    body: [{ version: 1, ...file }],
  }
}
for (const item of Object.values(EVIDENCE)) {
  defaultRoutes[`GET /evidence/${item.id}/quote`] = { status: 200, body: item }
}

/** A server-sent stream for one run, as `GET /jobs/{id}/events` writes it. */
export function eventStream(events) {
  return events
    .map((event, index) => {
      const seq = index + 1
      const data = { seq, job_id: JOB, at, payload: {}, ...event }
      return `id: ${String(seq)}\nevent: ${data.type}\ndata: ${JSON.stringify(data)}\n\n`
    })
    .join('')
}
