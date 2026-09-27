import { useEffect, useRef, useState, type ReactNode } from 'react'
import { api } from '../../api/endpoints.ts'
import { auditApi } from '../../api/audit.ts'
import { AppSidebar } from '../../app/AppSidebar.tsx'
import { navigate } from '../../app/navigate.ts'
import { auditHref, type AuditTab } from '../../app/route.ts'
import { reviewFields, pending } from '../../audit/review.ts'
import { JobProvider, useJob } from '../../state/job.tsx'
import { jobKey, useResource } from '../../state/resource.ts'
import { Button } from '../../ui/Button.tsx'
import { FailureNotice } from '../../ui/Feedback.tsx'
import { Tabs } from '../../ui/Nav.tsx'
import { Content, Window } from '../../ui/Shell.tsx'
import { ActivityPanel } from '../../ui/Activity.tsx'
import { rel } from '../../lib/format.ts'
import { StructureActivity } from './StructureActivity.tsx'
import { ReviewActivity } from './ReviewActivity.tsx'
import { DocumentsTab, type DocumentFilter } from './DocumentsTab.tsx'
import { DocumentsActivity } from './DocumentsActivity.tsx'
import { ReviewTab } from './ReviewTab.tsx'
import { StructureTab } from './StructureTab.tsx'
import { JournalTab } from './JournalTab.tsx'
import { ReadingsTab } from './ReadingsTab.tsx'
import { AuditStepper } from './AuditStepper.tsx'
import { RunActivity } from './RunActivity.tsx'
import { AuditExportScreen } from './AuditExportScreen.tsx'
import { ReportScreen } from './ReportScreen.tsx'
import './audit.css'
import './audit-work-visual.css'

export type AuditJobScreenProps = { jobId: string; tab: AuditTab; field: string | null }

export function AuditJobScreen({ jobId, tab, field }: AuditJobScreenProps) {
  if (tab === 'raport') return <ReportScreen jobId={jobId} />
  if (tab === 'predare') return <AuditExportScreen jobId={jobId} />
  return (
    <JobProvider key={jobId} jobId={jobId}>
      <AuditWork tab={tab} field={field} />
    </JobProvider>
  )
}

function AuditWork({ tab, field }: { tab: AuditTab; field: string | null }) {
  const ctx = useJob()
  const [documentFilter, setDocumentFilter] = useState<DocumentFilter>('all')
  const refreshedRun = useRef<string | null>(null)
  const currentRun = ctx.run
  const refresh = ctx.refresh
  useEffect(() => {
    if (!currentRun || currentRun.state === 'running' || refreshedRun.current === currentRun.runId)
      return
    refreshedRun.current = currentRun.runId
    refresh('documents', 'outline', 'visit')
  }, [currentRun, refresh])
  const { jobId } = ctx
  const documents = useResource(jobKey(jobId, 'documents'), () => auditApi.documents(jobId))
  const outline = useResource(jobKey(jobId, 'outline'), () => auditApi.outline(jobId))
  const overview = useResource('overview', api.overview)
  const fields = ctx.fields.data ?? []
  const review = reviewFields(fields)
  const waiting = review.filter(pending).length
  const photos = fields.filter(
    (item) => item.key.startsWith('meter.') || item.key.startsWith('thermal.'),
  )
  const hasVisit = Boolean(documents.data?.visit || photos.some((item) => item.needs_confirmation))
  const photoPending = photos.filter(
    (item) => item.needs_confirmation && item.review === 'pending',
  ).length
  const year = ctx.job.data?.year ?? ''
  const name = ctx.client.data?.name ?? ctx.job.data?.client_slug ?? ''
  const jobOverview = overview.data?.find((item) => item.id === jobId)
  const tabs = [
    {
      id: 'documente',
      label: 'Documente',
      count: documents.data
        ? documents.data.files.length +
          Number(Boolean(documents.data.anexa)) +
          Number(Boolean(documents.data.measures))
        : undefined,
    },
    {
      id: 'structura',
      label: 'Structura raportului',
      count: outline.data
        ? `${String(outline.data.written)}/${String(outline.data.chapters)}`
        : undefined,
    },
    { id: 'revizuire', label: 'Revizuire', count: waiting, pending: waiting > 0 },
    ...(hasVisit
      ? [{ id: 'masuratori', label: 'Măsurători', count: photoPending, pending: photoPending > 0 }]
      : []),
    { id: 'jurnal', label: 'Jurnal' },
  ]
  const loadError = ctx.job.error || ctx.fields.error || documents.error || outline.error
  const ready = ctx.job.data && ctx.fields.data && documents.data && outline.data
  let body: ReactNode
  if (loadError && !ready)
    body = (
      <FailureNotice
        title="Nu am putut încărca auditul"
        actions={
          <Button
            variant="secondary"
            height={30}
            onClick={() => {
              ctx.refresh('job', 'fields', 'documents', 'outline')
            }}
          >
            Încearcă din nou
          </Button>
        }
      >
        {loadError instanceof Error ? loadError.message : 'Cererea nu poate fi procesată.'}
      </FailureNotice>
    )
  else if (!documents.data || !outline.data || !ctx.job.data || !ctx.fields.data)
    body = <p className="app-loading">Se încarcă…</p>
  else if (tab === 'documente')
    body = (
      <DocumentsTab
        documents={documents.data}
        filter={documentFilter}
        setFilter={setDocumentFilter}
      />
    )
  else if (tab === 'revizuire') body = <ReviewTab field={field} outline={outline.data} />
  else if (tab === 'structura') body = <StructureTab outline={outline.data} />
  else if (tab === 'masuratori') body = <ReadingsTab field={field} />
  else body = <JournalTab outline={outline.data} />
  return (
    <Window activity>
      <AppSidebar activeJobId={jobId} count={waiting} working={ctx.run?.state === 'running'} />
      <Content
        crumb={`${name} ${String(year)}`}
        title={`Audit energetic ${String(year)}`}
        actions={
          <>
            <span className="audit-saved">
              salvat {jobOverview?.updated_at ? rel(jobOverview.updated_at) : 'acum'}
            </span>
            <Button
              variant="secondary"
              height={34}
              onClick={() => {
                navigate(auditHref(jobId, 'raport'))
              }}
            >
              Previzualizare
            </Button>
            <Button
              height={34}
              disabled={ctx.run?.state === 'running'}
              onClick={() => {
                navigate(auditHref(jobId, 'predare'))
              }}
            >
              Exportă Word
            </Button>
          </>
        }
      >
        {(tab === 'documente' || tab === 'revizuire') && documents.data && (
          <div className="audit-header-stepper">
            <AuditStepper
              documents={documents.data}
              fields={fields}
              outputs={ctx.outputs.data ?? []}
            />
          </div>
        )}
        <Tabs
          active={tab}
          items={tabs}
          onSelect={(selected) => {
            navigate(auditHref(jobId, selected as AuditTab))
          }}
        />
        <div className="audit-body">{body}</div>
      </Content>
      <ActivityPanel
        title={tab === 'structura' ? 'Secţiuni fără răspuns' : 'Ce s-a întâmplat'}
        onAll={() => {
          navigate(auditHref(jobId, 'jurnal'))
        }}
      >
        {ctx.run?.state === 'running' && (
          <RunActivity
            run={ctx.run}
            onStop={() => {
              void api.cancel(jobId).then(() => {
                ctx.refresh('job', 'status')
              })
            }}
          />
        )}
        {tab === 'structura' && outline.data ? (
          <StructureActivity outline={outline.data} />
        ) : tab === 'revizuire' && outline.data ? (
          <ReviewActivity fields={review} outline={outline.data} />
        ) : tab === 'documente' && documents.data ? (
          <DocumentsActivity
            documents={documents.data}
            status={ctx.status.data}
            setFilter={setDocumentFilter}
          />
        ) : (
          ctx.log.data
            ?.slice(-6)
            .reverse()
            .map((decision) => <p key={decision.id}>{decision.field_id}</p>)
        )}
      </ActivityPanel>
    </Window>
  )
}
