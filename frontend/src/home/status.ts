import type { JobOverview } from '../api/types.ts'

export function statusLine(job: JobOverview): string {
  if (job.state === 'running') return 'se lucrează…'
  if (job.readiness_error) return 'aşteaptă documentele'
  if (job.final_ok) return 'gata de exportul final'
  return job.next ?? 'în lucru'
}
