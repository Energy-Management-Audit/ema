import type { JobOverview } from '../api/types.ts'

const ORDER = { audit: 0, invoices: 1, piee: 2, reporting: 3 }

export type ClientGroup = {
  slug: string
  name: string
  color: 'olive' | 'violet'
  jobs: JobOverview[]
}

export function groupInProgress(jobs: JobOverview[]): ClientGroup[] {
  const grouped = new Map<string, JobOverview[]>()
  for (const job of jobs) {
    if (job.finalized || job.type === 'reporting') continue
    const existing = grouped.get(job.client_slug) ?? []
    existing.push(job)
    grouped.set(job.client_slug, existing)
  }
  return [...grouped.entries()]
    .sort(
      (a, b) =>
        Math.max(...b[1].map((job) => Date.parse(job.updated_at))) -
        Math.max(...a[1].map((job) => Date.parse(job.updated_at))),
    )
    .map(([slug, items], index) => ({
      slug,
      name: items.find((job) => job.client_name)?.client_name ?? slug,
      color: index % 2 === 0 ? ('olive' as const) : ('violet' as const),
      jobs: items.sort((a, b) => ORDER[a.type] - ORDER[b.type] || (b.year ?? 0) - (a.year ?? 0)),
    }))
}

export function jobLabel(job: JobOverview): string {
  if (job.type === 'audit') return `Audit energetic ${String(job.year ?? '')}`.trim()
  if (job.type === 'piee') return `PIEE ${String(job.year ?? '')}`.trim()
  return job.year === null ? 'Facturi' : `Facturi ${String(job.year)}`
}

export function finalizedJobs(jobs: JobOverview[]): JobOverview[] {
  return jobs
    .filter((job) => job.finalized && job.type !== 'reporting')
    .sort((a, b) => (b.approved_at ?? b.updated_at).localeCompare(a.approved_at ?? a.updated_at))
}

export function finalizedLabel(job: JobOverview): string {
  const type = job.type === 'audit' ? 'Audit' : job.type === 'piee' ? 'PIEE' : 'Facturi'
  return `${type} ${job.client_name ?? job.client_slug} ${String(job.year ?? '')}`.trim()
}

export function moreLabel(count: number): string {
  if (count === 1) return 'încă una…'
  if (count === 2) return 'încă două…'
  return `încă ${String(count)}…`
}
