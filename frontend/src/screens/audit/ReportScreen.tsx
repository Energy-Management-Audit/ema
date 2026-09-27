import { useEffect, useRef, useState } from 'react'
import { auditReport, runFailure } from '../../api/audit-report.ts'
import { api } from '../../api/endpoints.ts'
import { AppSidebar } from '../../app/AppSidebar.tsx'
import { navigate } from '../../app/navigate.ts'
import { auditHref } from '../../app/route.ts'
import { draftSummary, pageIndex, tocItems } from '../../audit/report.ts'
import { formatBytes } from '../../lib/format.ts'
import { JobProvider, useJob } from '../../state/job.tsx'
import { invalidateJob, jobKey, useResource } from '../../state/resource.ts'
import { Button } from '../../ui/Button'
import { FailureNotice, ProgressBar } from '../../ui/Feedback'
import { Content, Window } from '../../ui/Shell'
import { ProblemNotice, download, useAction } from '../actions.tsx'
import { clientName } from '../JobScreen.tsx'
import { RegenerateDialog } from '../RegenerateDialog.tsx'
import { problemTitle } from '../States.tsx'
import { PdfPages, usePdfDocument, type PdfPagesHandle } from './PdfPages.tsx'
import { ReportPanel } from './ReportPanel.tsx'
import { ReportToc } from './ReportToc.tsx'
import './report.css'

export type ReportScreenProps = { jobId: string }

const RENDER_STAGES = new Set(['audit_render', 'audit_final'])

export function ReportScreen({ jobId }: ReportScreenProps) {
  return (
    <JobProvider jobId={jobId}>
      <ReportView />
    </JobProvider>
  )
}

/** A render the screen follows refetches the report and the approvals when it ends. */
export function useRenderEnd(jobId: string): void {
  const { run } = useJob()
  const ended = run && RENDER_STAGES.has(run.stage) && run.state !== 'running'
  const key = ended ? `${run.runId}:${run.state}` : null
  useEffect(() => {
    if (key) invalidateJob(jobId, 'report', 'approvals')
  }, [jobId, key])
}

/** The message a failed run left in its `stage_failed` event, else the run's stored error. */
export function useFailure(jobId: string, runId: string | null, failed: boolean) {
  const ctx = useJob()
  const failure = useResource(failed && runId ? jobKey(jobId, `failure/${runId}`) : null, () =>
    runFailure(jobId, runId ?? ''),
  )
  const error = ctx.status.data?.runs.find((item) => item.id === runId)?.error ?? ''
  return { message: failure.data?.message ?? null, error }
}

function ReportView() {
  const ctx = useJob()
  const { jobId } = ctx
  const report = useResource(jobKey(jobId, 'report'), () => auditReport.report(jobId))
  const start = useAction()
  const save = useAction()
  const [confirming, setConfirming] = useState(false)
  const pagesRef = useRef<PdfPagesHandle>(null)
  const markersRef = useRef<HTMLDivElement>(null)
  useRenderEnd(jobId)

  const job = ctx.job.data
  const year = job?.year ?? ''
  const run = ctx.run
  const running = run?.state === 'running' && RENDER_STAGES.has(run.stage)
  const draft = report.data?.draft ?? null
  const summary = draftSummary(report.data)
  const outputs = ctx.outputs.data ?? []
  const docx = outputs.find((item) => item.id === draft?.docx_output_id) ?? null
  const pdf = usePdfDocument(jobId, draft?.state === 'ready' ? draft.pdf_output_id : null)
  const failed = !running && draft?.state === 'failed'
  const failure = useFailure(jobId, draft?.run_id ?? null, failed)
  const items = tocItems(summary, {
    running,
    done: run?.done ?? 0,
    total: run?.total ?? 0,
  })

  const generate = () => {
    if (!job) return
    setConfirming(false)
    void start.run(async () => {
      const started = await auditReport.startRender(jobId, job.revision)
      ctx.follow(started.run_id, started.stage)
      ctx.refresh('job', 'status')
    })
  }
  const stop = useAction()
  const crumb = (
    <a className="report__crumb" href={auditHref(jobId, 'structura')}>
      {`${clientName(ctx)} ${String(year)} · Audit energetic ${String(year)}`}
    </a>
  )
  const actions = (
    <>
      <span className="report__template">Şablon: EMA 2026</span>
      {running ? (
        <Button height={34} loading>
          Se scrie…
        </Button>
      ) : (
        <Button
          height={34}
          disabled={!job || start.pending}
          loading={start.pending}
          onClick={() => {
            if (docx?.edited_externally) setConfirming(true)
            else generate()
          }}
        >
          Generează ciorna
        </Button>
      )}
    </>
  )

  let centre
  if (report.error && !report.data) {
    centre = (
      <FailureNotice
        title="Nu am putut încărca raportul"
        actions={
          <Button
            variant="secondary"
            height={30}
            onClick={() => {
              ctx.refresh('report')
            }}
          >
            Încearcă din nou
          </Button>
        }
      >
        {problemTitle(report.error)}
      </FailureNotice>
    )
  } else if (!report.data) {
    centre = <p className="report__loading">Se încarcă…</p>
  } else if (pdf.doc) {
    centre = <PdfPages ref={pagesRef} doc={pdf.doc} pages={pdf.pages} />
  } else if (pdf.failed) {
    centre = (
      <FailureNotice
        title="Previzualizarea nu s-a putut încărca"
        actions={
          <Button variant="secondary" height={30} onClick={pdf.retry}>
            Încearcă din nou
          </Button>
        }
      >
        Ciorna rămâne întreagă; se poate descărca din panoul din dreapta.
      </FailureNotice>
    )
  } else if (report.data.word || !docx) {
    centre = (
      <p className="report__empty">
        {draft?.pdf_output_id ? 'Se încarcă…' : 'Previzualizarea apare după prima ciornă.'}
      </p>
    )
  } else {
    centre = (
      <div className="report__empty">
        <p>Previzualizarea cere Microsoft Word. Ciorna se poate descărca.</p>
        <Button
          variant="secondary"
          height={32}
          loading={save.pending}
          onClick={() => {
            void save.run(() => download(jobId, docx))
          }}
        >
          Descarcă ciorna
        </Button>
      </div>
    )
  }

  return (
    <Window activity>
      <AppSidebar activeJobId={jobId} working={job?.state === 'running'} />
      <Content crumb={crumb} title="Raport Word" actions={actions}>
        <div className="report">
          {running && (
            <div className="report__progress" data-testid="report-progress">
              <div className="report__progress-text">
                <div className="report__progress-line">
                  <strong>{run.message}</strong>
                  <span className="report__count">{`${String(run.done)} / ${String(run.total)} capitole`}</span>
                </div>
                <ProgressBar
                  value={run.total > 0 ? Math.round((run.done / run.total) * 100) : 0}
                  running
                />
              </div>
              <Button
                variant="secondary"
                height={34}
                disabled={stop.pending}
                onClick={() => {
                  void stop.run(async () => {
                    await api.cancel(jobId)
                    ctx.refresh('job', 'status')
                  })
                }}
              >
                Opreşte
              </Button>
            </div>
          )}
          {start.problem &&
            (start.problem.code === 'audit_base_missing' ? (
              <FailureNotice title={start.problem.title} actions={null}>
                {''}
              </FailureNotice>
            ) : (
              <ProblemNotice problem={start.problem} />
            ))}
          <ProblemNotice problem={stop.problem ?? save.problem} />
          {failed && (
            <FailureNotice
              title="Raportul nu s-a generat"
              actions={
                <Button variant="secondary" height={30} onClick={generate}>
                  Încearcă din nou
                </Button>
              }
            >
              {failure.message ?? failure.error}
            </FailureNotice>
          )}
          <div className="report__body">
            <ReportToc
              items={items}
              markers={summary?.markers.length ?? 0}
              onJump={
                pdf.doc
                  ? (page) => {
                      const index = pageIndex(page, pdf.pages)
                      if (index !== null) pagesRef.current?.scrollToPage(index)
                    }
                  : undefined
              }
              onMarkers={() => {
                markersRef.current?.focus()
              }}
            />
            <div className="report__preview">{centre}</div>
          </div>
        </div>
      </Content>
      <ReportPanel
        summary={summary}
        markersRef={markersRef}
        file={docx ? { name: docx.name, size: formatBytes(docx.size_bytes) } : null}
        downloading={save.pending}
        onDownload={
          docx
            ? () => {
                void save.run(() => download(jobId, docx))
              }
            : undefined
        }
        onFill={() => {
          navigate(auditHref(jobId, 'revizuire'))
        }}
      />
      {confirming && docx && (
        <RegenerateDialog
          name={docx.name}
          onClose={() => {
            setConfirming(false)
          }}
          onConfirm={generate}
        />
      )}
    </Window>
  )
}
