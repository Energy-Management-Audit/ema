import { CLIENT_OVERVIEW } from './default.mjs'

const year = new Date().getFullYear() - 1

export const REPORT_CLIENTS = CLIENT_OVERVIEW.slice(0, 2).map((client) => ({
  ...client,
  annex_years: [year - 1, year],
}))

export const READY_RUN = {
  id: 'report-run-1',
  job_id: 'report-job-1',
  created_at: '2026-09-27T09:00:00Z',
  years: [year - 2, year - 1, year],
  client_ids: REPORT_CLIENTS.map((client) => client.id),
  state: 'ready',
  output_id: 'report-output-1',
  exceptions: [
    {
      client_id: REPORT_CLIENTS[0].id,
      year,
      code: 'REVIZUIRE',
      detail: 'Costul lipseşte.',
      source_name: 'Anexa-Exemplu.xlsx',
      beneficiary: REPORT_CLIENTS[0].name,
      decision: 'Se verifică în anexă.',
      ref: 'Anexa 2–3 · D12',
    },
    {
      client_id: REPORT_CLIENTS[1].id,
      year,
      code: 'INFORMARE',
      detail: 'Măsura nu are economie.',
      source_name: 'Anexa-Industrial.xlsx',
      beneficiary: REPORT_CLIENTS[1].name,
      decision: null,
      ref: 'Anexa 2–3 · F14',
    },
  ],
}

export const REPORT_PREVIEW = {
  years: READY_RUN.years,
  read: 2,
  companies_per_year: { [String(year - 2)]: 0, [String(year - 1)]: 1, [String(year)]: 2 },
  rows: {
    [String(year - 2)]: [],
    [String(year - 1)]: [],
    [String(year)]: REPORT_CLIENTS.map((client, index) => ({
      nr: index + 1,
      beneficiary: client.name,
      client_id: client.id,
      measures: [
        {
          description: index === 0 ? 'Modernizare iluminat' : 'Izolare termică',
          saving_tep: index === 0 ? 12.5 : null,
          cost_thousand_lei: index === 0 ? null : 45.2,
        },
      ],
    })),
  },
}

export const REPORT_ROUTES = {
  'GET /clients/overview': { status: 200, body: REPORT_CLIENTS },
  'GET /reporting/runs': { status: 200, body: [READY_RUN] },
  'GET /reporting/runs/report-run-1/preview': { status: 200, body: REPORT_PREVIEW },
  'GET /jobs/report-job-1/outputs/report-output-1': {
    status: 200,
    contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    body: 'synthetic workbook',
  },
}
