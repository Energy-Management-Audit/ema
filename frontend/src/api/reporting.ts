import { request } from './client.ts'
import type { ReportingPreview, ReportingRun } from './reporting-types.ts'

const path = (id: string) => `/reporting/runs/${encodeURIComponent(id)}`

export const reportingApi = {
  runs: () => request<ReportingRun[]>('GET', '/reporting/runs'),
  startRun: (years: number[], clientIds: string[]) =>
    request<ReportingRun>('POST', '/reporting/runs', { years, client_ids: clientIds }),
  run: (id: string) => request<ReportingRun>('GET', path(id)),
  preview: (id: string) => request<ReportingPreview>('GET', `${path(id)}/preview`),
}
