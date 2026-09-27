import { ChevronRight } from 'lucide-react'
import type { JobOverview } from '../../api/types.ts'
import { jobPath } from '../../app/route.ts'
import { jobLabel } from '../../app/sidebar.ts'
import { navigate } from '../../app/navigate.ts'
import { rel } from '../../lib/format.ts'
import { statusLine } from '../../home/status.ts'
import { ListRow } from '../../ui/Rows.tsx'
import { Icon } from '../../ui/Icon.tsx'

export function HomeJobRow({ job }: { job: JobOverview }) {
  return (
    <ListRow className="home-job-row">
      <a
        href={jobPath(job)}
        onClick={(event) => {
          event.preventDefault()
          navigate(jobPath(job))
        }}
      >
        <strong>{jobLabel(job)}</strong>
        <span>
          {job.client_name ?? job.client_slug} {job.year ?? ''} · {statusLine(job)}
        </span>
      </a>
      <span className="home-job-row__time">{rel(job.updated_at)}</span>
      <Icon icon={ChevronRight} size={14} stroke={1.8} />
    </ListRow>
  )
}
