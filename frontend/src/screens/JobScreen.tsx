import type { ReactNode } from 'react'
import { jobHref, type Tab } from '../app/route.ts'
import { AppSidebar } from '../app/AppSidebar.tsx'
import { navigate } from '../app/navigate.ts'
import { analysisYears } from '../piee/dataset.ts'
import { blockingIssues } from '../piee/readiness.ts'
import { useJob } from '../state/job.tsx'
import { Button } from '../ui/Button'
import { FailureNotice } from '../ui/Feedback'
import { Tabs } from '../ui/Nav'
import { Content, Window } from '../ui/Shell'
import { ActivityColumn } from './BlockingPanel.tsx'
import { DataTab } from './DataTab.tsx'
import { DocumentsTab } from './DocumentsTab.tsx'
import { ExportScreen } from './ExportScreen.tsx'
import { JobActions, useSlotCount } from './JobHeader.tsx'
import { JournalTab } from './JournalTab.tsx'
import { MeasuresTab } from './MeasuresTab.tsx'
import { problemTitle } from './States.tsx'
import './screens.css'

export function clientName(ctx: ReturnType<typeof useJob>): string {
  return ctx.client.data?.name ?? ctx.job.data?.client_slug ?? ''
}

export function JobScreen({ tab, field }: { tab: Tab; field: string | null }) {
  const ctx = useJob()
  const { checks, jobId } = ctx
  const count = blockingIssues(checks.data).length
  const sidebar = (
    <AppSidebar activeJobId={jobId} count={count} working={ctx.run?.state === 'running'} />
  )
  if (tab === 'predare') {
    return (
      <Window>
        {sidebar}
        <ExportScreen />
      </Window>
    )
  }
  return (
    <Window activity>
      {sidebar}
      <JobContent tab={tab} field={field} />
      <ActivityColumn tab={tab} />
    </Window>
  )
}

function JobContent({ tab: current, field: camp }: { tab: Tab; field: string | null }) {
  const ctx = useJob()
  const { job, jobId } = ctx
  const years = analysisYears(ctx.fields.data ?? [])
  const range = years.length ? `${String(years[0])}–${String(years.at(-1))}` : ''
  const slots = useSlotCount(jobId)
  const year = job.data?.year ?? ''
  let body: ReactNode
  if (job.error && !job.data) {
    body = (
      <FailureNotice
        title="Nu am putut încărca lucrarea"
        actions={
          <Button
            variant="secondary"
            height={32}
            onClick={() => {
              ctx.refresh('job', 'checks')
            }}
          >
            Încearcă din nou
          </Button>
        }
      >
        {problemTitle(job.error)}
      </FailureNotice>
    )
  } else if (!job.data) {
    body = <p className="app-loading">Se încarcă…</p>
  } else if (current === 'documente') body = <DocumentsTab />
  else if (current === 'date') body = <DataTab camp={camp} />
  else if (current === 'masuri') body = <MeasuresTab />
  else body = <JournalTab />
  const title = `PIEE ${String(year)}${current === 'date' && range ? ` · analiza ${range}` : ''}`
  return (
    <Content
      crumb={job.data ? `${clientName(ctx)} ${String(year)}` : ''}
      title={title}
      actions={<JobActions tab={current} />}
    >
      <Tabs
        active={current}
        onSelect={(id) => {
          navigate(jobHref(jobId, id as Tab))
        }}
        items={[
          { id: 'documente', label: 'Documente', count: slots ?? undefined },
          { id: 'date', label: range ? `Date ${range}` : 'Date' },
          {
            id: 'masuri',
            label: 'Măsuri',
            count: ctx.summary.data ? ctx.summary.data.measures_total : undefined,
          },
          { id: 'jurnal', label: 'Jurnal' },
        ]}
      />
      <div className="job-body">{body}</div>
    </Content>
  )
}
