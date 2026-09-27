// Synthetic cross-workflow data shared by screen harnesses.

const at = '2026-09-27T08:00:00+00:00'

export const CLIENTS = [
  {
    id: 'client-exemplu',
    name: 'Exemplu Energie SA',
    cui: 'RO1234567',
    caen: null,
    sites: [],
    contacts: [],
    revision: 1,
    anaf_refreshed_at: null,
  },
  {
    id: 'client-doi',
    name: 'Doi Industrie SRL',
    cui: 'RO7654321',
    caen: null,
    sites: [],
    contacts: [],
    revision: 1,
    anaf_refreshed_at: null,
  },
]

export const JOBS = [
  {
    id: 'job-piee-1',
    type: 'piee',
    client_slug: 'client-exemplu',
    year: 2026,
    state: 'ready',
    revision: 7,
  },
  {
    id: 'job-audit-1',
    type: 'audit',
    client_slug: 'client-doi',
    year: 2026,
    state: 'open',
    revision: 1,
  },
  {
    id: 'job-invoices-1',
    type: 'invoices',
    client_slug: 'client-exemplu',
    year: 2026,
    state: 'created',
    revision: 1,
  },
]

export const OVERVIEW = JOBS.map((job, index) => ({
  ...job,
  client_name: CLIENTS.find((client) => client.id === job.client_slug)?.name ?? null,
  created_at: at,
  updated_at: `2026-09-27T08:0${String(index)}:00+00:00`,
  final_ok: false,
  blocking: index === 0 ? 1 : null,
  next: null,
  readiness_error: index === 2 ? 'invoices_missing' : null,
  approved_at: null,
  finalized: false,
}))

export const baseRoutes = {
  'POST /session': { status: 200, body: { csrf: 'csrf-token' } },
  'GET /settings': {
    status: 200,
    body: {
      theme: 'light',
      default_provider: null,
      providers: {
        gemini: { present: false, verified_at: null, hint: null, source: null },
        openai: { present: false, verified_at: null, hint: null, source: null },
      },
      extraction: { ocr: true, flag_uncertain: true, auto_accept_exact: false },
      workspace: '/synthetic/workspace',
      backup: { dir: null, last_at: null, last_size: null, last_name: null, due: true },
    },
  },
  'GET /settings/update': {
    status: 200,
    body: {
      current: '0.1.0',
      latest: null,
      newer: false,
      notes: null,
      page_url: null,
      download_url: null,
      checked_at: at,
      state: 'no_release',
    },
  },
  'GET /jobs': { status: 200, body: JOBS },
  'GET /jobs/overview': { status: 200, body: OVERVIEW },
  'GET /clients': { status: 200, body: CLIENTS },
}
