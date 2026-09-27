import { CLIENTS, OVERVIEW } from '../base.mjs'

const year = new Date().getFullYear() - 1

export const CLIENT_OVERVIEW = [
  ...CLIENTS.map((client, index) => ({
    id: client.id,
    name: client.name,
    cui: client.cui,
    county: index === 0 ? 'Braşov' : 'Ilfov',
    caen: index === 0 ? '3511' : '2410',
    caen_description: index === 0 ? 'Producţie de energie' : 'Industrie',
    anaf_refreshed_at: index === 0 ? '2026-09-01T08:00:00Z' : null,
    annex_years: index === 0 ? [year] : [],
    consumption: index === 0 ? { year, total_tep: '1234.56' } : null,
    pods: index === 0 ? ['RO001234567890123456'] : [],
  })),
  ...Array.from({ length: 8 }, (_, index) => ({
    id: `client-extra-${String(index)}`,
    name: `Exemplu Industrial ${String(index)} SRL`,
    cui: `RO2345678${String(index)}`,
    county: 'Cluj',
    caen: '2511',
    caen_description: 'Producţie',
    anaf_refreshed_at: null,
    annex_years: index < 3 ? [year] : [],
    consumption: index < 3 ? { year, total_tep: String(100 + index) } : null,
    pods: [],
  })),
]

export const PROFILE = {
  client: {
    ...CLIENTS[0],
    sites: [],
    contacts: [{ id: 'manager', name: 'Manager Exemplu', role: 'energy_manager' }],
  },
  identification: {
    name: 'Exemplu Energie SA',
    cui: '1234567',
    registration: 'J08/1/2020',
    address: 'Strada Exemplu 1',
    caen: '3511',
    caen_description: 'Producţie de energie',
    source: 'anaf',
    retrieved_at: '2026-09-01T08:00:00Z',
    annex_year: null,
  },
  fiscal: { active: true, vat_payer: true },
  energy_manager: { id: 'manager', name: 'Manager Exemplu', role: 'energy_manager' },
  contact_person: null,
  memory: [
    {
      kind: 'pod',
      identifier: 'RO001234567890123456',
      job_id: 'job-invoices-1',
      confirmed_at: '2026-09-01T08:00:00Z',
      active: false,
    },
  ],
  annexes: [
    {
      sha: 'synthetic-sha',
      year,
      file_name: 'Anexa-Exemplu.xlsx',
      read_at: '2026-09-01T08:00:00Z',
    },
  ],
}

export const CLIENT_ROUTES = {
  'GET /clients/overview': { status: 200, body: CLIENT_OVERVIEW },
  'GET /clients/client-exemplu/profile': { status: 200, body: PROFILE },
  'GET /jobs/overview': { status: 200, body: OVERVIEW },
}
