// One function per contract call of the audit report and its export (S17b audit-report).

import { request } from './client.ts'
import { subscribeRun } from './events.ts'
import type { AuditReport, AuditSection, RunFailure } from './audit-report-types.ts'
import type { RunStart } from './types.ts'

const job = (id: string) => `/jobs/${encodeURIComponent(id)}`

export const auditReport = {
  report: (id: string) => request<AuditReport>('GET', `${job(id)}/audit/report`),
  sections: (id: string) => request<AuditSection[]>('GET', `${job(id)}/sections`),
  startRender: (id: string, revision: number) =>
    request<RunStart>('POST', `${job(id)}/stages/audit_render`, { on_revision: revision }),
  startFinal: (id: string, revision: number) =>
    request<RunStart>('POST', `${job(id)}/stages/audit_final`, { on_revision: revision }),
}

/** Why a finished run failed, read from its own `stage_failed` event (replayed by the stream). */
export function runFailure(jobId: string, runId: string): Promise<RunFailure | null> {
  return new Promise((resolve) => {
    let settled = false
    const done = (value: RunFailure | null) => {
      if (settled) return
      settled = true
      resolve(value)
    }
    const stop = subscribeRun(
      jobId,
      runId,
      (event) => {
        if (event.type === 'stage_failed') {
          const { code, message } = event.payload
          done({
            code: typeof code === 'string' ? code : 'stage_failed',
            message: typeof message === 'string' ? message : null,
          })
          stop()
        } else if (event.type === 'stage_finished' || event.type === 'stage_cancelled') {
          done(null)
          stop()
        }
      },
      () => {
        done(null)
      },
    )
  })
}
