// One function per Contract call of the PIEE journey; nothing else calls `request`.

import { blob, request } from './client.ts'
import type {
  Approval,
  CancelResult,
  Client,
  ClientFile,
  Decision,
  DeleteResult,
  Evidence,
  ExportChecks,
  ExportResult,
  Field,
  FileVersion,
  Job,
  JobOverview,
  JobStatus,
  Output,
  NewJobResult,
  PieeSummary,
  PrelucrareState,
  RunStart,
  SessionResult,
  SettingsView,
  SlotVersion,
  VisitView,
} from './types.ts'

const job = (id: string) => `/jobs/${encodeURIComponent(id)}`

export const api = {
  session: (code: string) => request<SessionResult>('POST', '/session', { code }),
  settings: () => request<SettingsView>('GET', '/settings'),
  jobs: () => request<Job[]>('GET', '/jobs'),
  overview: () => request<JobOverview[]>('GET', '/jobs/overview'),
  createJob: (type: 'audit' | 'piee' | 'invoices', client: string, year: number) =>
    request<NewJobResult>('POST', '/jobs', { type, client, year }),
  deleteJob: (id: string, revision: number) =>
    request<DeleteResult>('DELETE', job(id), { confirm: true, on_revision: revision }),
  startStage: (id: string, stage: string, revision: number) =>
    request<RunStart>('POST', `${job(id)}/stages/${encodeURIComponent(stage)}`, {
      on_revision: revision,
    }),
  removeVersion: (id: string, slot: string, version: number, revision: number) =>
    request<DeleteResult>(
      'DELETE',
      `${job(id)}/slots/${encodeURIComponent(slot)}/versions/${String(version)}`,
      { confirm: true, on_revision: revision },
    ),
  evidenceSnippet: (id: string, highlight: boolean) =>
    blob(`/evidence/${encodeURIComponent(id)}/snippet.png?highlight=${highlight ? '1' : '0'}`),
  evidencePage: (id: string) => blob(`/evidence/${encodeURIComponent(id)}/page.png`),
  clients: () => request<Client[]>('GET', '/clients'),
  client: (id: string) => request<Client>('GET', `/clients/${encodeURIComponent(id)}`),
  job: (id: string) => request<Job>('GET', job(id)),
  status: (id: string) => request<JobStatus>('GET', `${job(id)}/status`),
  fields: (id: string) => request<Field[]>('GET', `${job(id)}/fields`),
  visit: (id: string) => request<VisitView>('GET', `${job(id)}/visit`),
  startReadings: (id: string, revision: number) =>
    request<RunStart>('POST', `${job(id)}/stages/readings`, { on_revision: revision }),
  accept: (id: string, fieldId: string, revision: number) =>
    request<Decision>('POST', `${job(id)}/fields/${encodeURIComponent(fieldId)}/decide`, {
      action: 'accept',
      on_revision: revision,
    }),
  missing: (id: string) => request<Field[]>('GET', `${job(id)}/fields?status=missing`),
  conflicts: (id: string) => request<Field[]>('GET', `${job(id)}/conflicts`),
  readDocuments: (id: string, revision: number) =>
    request<RunStart>('POST', `${job(id)}/piee/import`, { on_revision: revision }),
  choose: (id: string, fieldId: string, candidateId: string, revision: number) =>
    request<Decision>('POST', `${job(id)}/conflicts/${encodeURIComponent(fieldId)}`, {
      candidate_id: candidateId,
      on_revision: revision,
    }),
  correct: (id: string, fieldId: string, value: string, revision: number) =>
    request<Decision>('POST', `${job(id)}/fields/${encodeURIComponent(fieldId)}/decide`, {
      action: 'correct',
      on_revision: revision,
      value,
    }),
  log: (id: string) => request<Decision[]>('GET', `${job(id)}/log`),
  undo: (id: string, decisionId: string) =>
    request<Decision>('POST', `${job(id)}/log/${encodeURIComponent(decisionId)}/undo`),
  evidence: (evidenceId: string) =>
    request<Evidence>('GET', `/evidence/${encodeURIComponent(evidenceId)}/quote`),
  checks: (id: string) => request<ExportChecks>('GET', `${job(id)}/export/checks`),
  summary: (id: string) => request<PieeSummary>('GET', `${job(id)}/piee/summary`),
  outputs: (id: string) => request<Output[]>('GET', `${job(id)}/outputs`),
  output: (id: string, outputId: string) =>
    blob(`${job(id)}/outputs/${encodeURIComponent(outputId)}`),
  approvals: (id: string) => request<Approval[]>('GET', `${job(id)}/approvals`),
  slots: (id: string) => request<string[]>('GET', `${job(id)}/slots`),
  slotVersions: (id: string, slot: string) =>
    request<SlotVersion[]>('GET', `${job(id)}/slots/${slot}/versions`),
  fileVersions: (client: string, sha: string) =>
    request<FileVersion[]>(
      'GET',
      `/clients/${encodeURIComponent(client)}/files/${encodeURIComponent(sha)}/versions`,
    ),
  prelucrare: (id: string) => request<PrelucrareState>('GET', `${job(id)}/prelucrare`),
  upload: (client: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<ClientFile>('POST', `/clients/${encodeURIComponent(client)}/files`, form)
  },
  putSlot: (id: string, slot: string, sha: string) =>
    request<SlotVersion>('PUT', `${job(id)}/slots/${slot}`, { file_sha: sha }),
  bindPrelucrare: (id: string, sha: string) =>
    request<PrelucrareState>('POST', `${job(id)}/prelucrare`, { file_id: sha, role: 'input' }),
  generate: (id: string, revision: number) =>
    request<RunStart>('POST', `${job(id)}/piee/generate`, { kind: 'draft', on_revision: revision }),
  generatePackage: (id: string, revision: number) =>
    request<RunStart>('POST', `${job(id)}/stages/piee_word`, { on_revision: revision }),
  cancel: (id: string) => request<CancelResult>('POST', `${job(id)}/cancel`),
  exportFinal: (id: string, outputId: string, readinessHash: string) =>
    request<ExportResult>('POST', `${job(id)}/export`, {
      final: true,
      output_id: outputId,
      readiness_hash: readinessHash,
      confirm: true,
    }),
}

export const eventsPath = (id: string) => `${job(id)}/events`
