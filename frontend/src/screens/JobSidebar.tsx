import { api } from '../api/endpoints.ts'
import type { Client, Job } from '../api/types.ts'
import { navigate } from '../app/navigate.ts'
import { auditHref, jobHref } from '../app/route.ts'
import { useResource } from '../state/resource.ts'
import { NavClient, NavGroup, NavJob, Sidebar, SidebarFooter } from '../ui/Shell'

/** PIEE and audit jobs grouped by client, in first-seen order (D6). */
export function groupJobs(jobs: Job[]): { slug: string; jobs: Job[] }[] {
  const groups: { slug: string; jobs: Job[] }[] = []
  for (const job of jobs) {
    if (job.type !== 'piee' && job.type !== 'audit') continue
    const group = groups.find((item) => item.slug === job.client_slug)
    if (group) group.jobs.push(job)
    else groups.push({ slug: job.client_slug, jobs: [job] })
  }
  return groups
}

export function JobSidebar({
  activeId,
  count,
  working,
}: {
  activeId?: string
  count?: number
  working?: boolean
}) {
  const jobs = useResource('jobs', () => api.jobs())
  const clients = useResource('clients', () => api.clients())
  const names = new Map((clients.data ?? []).map((client: Client) => [client.id, client.name]))
  return (
    <Sidebar footer={<SidebarFooter initials="AP" name="Auditor" />}>
      <NavGroup title="ÎN LUCRU">
        {groupJobs(jobs.data ?? []).flatMap((group) => [
          <NavClient key={`client-${group.slug}`} color="olive">
            {names.get(group.slug) ?? group.slug}
          </NavClient>,
          ...group.jobs.map((job) => {
            const active = job.id === activeId
            return (
              <NavJob
                key={job.id}
                active={active}
                working={active ? working : job.state === 'running'}
                count={active && count ? count : undefined}
                onClick={() => {
                  navigate(job.type === 'audit' ? auditHref(job.id) : jobHref(job.id, 'date'))
                }}
              >
                {job.type === 'audit' ? 'Audit energetic' : 'PIEE'} {job.year ?? ''}
              </NavJob>
            )
          }),
        ])}
      </NavGroup>
    </Sidebar>
  )
}
