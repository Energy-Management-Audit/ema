import { plural as countRo } from '../../lib/plural.ts'
import { useState } from 'react'
import { auditReport } from '../../api/audit-report.ts'
import { api } from '../../api/endpoints.ts'
import type { Output } from '../../api/types.ts'
import { AppSidebar } from '../../app/AppSidebar.tsx'
import { auditHref } from '../../app/route.ts'
import { EXPORT_STALE, auditChecks, canGenerateFinal } from '../../audit/report.ts'
import { formatBytes, rel } from '../../lib/format.ts'
import { JobProvider, useJob } from '../../state/job.tsx'
import { jobKey, useResource } from '../../state/resource.ts'
import { Button } from '../../ui/Button'
import { Status } from '../../ui/Chip'
import { FailureNotice } from '../../ui/Feedback'
import { DocThumb, ExportCheck, PackageFile } from '../../ui/Package'
import { Window } from '../../ui/Shell'
import { SectionKey } from '../../ui/Surface'
import {
  ProblemNotice,
  download,
  exportPackage,
  type ExportReceipt,
  useAction,
} from '../actions.tsx'
import { clientName } from '../JobScreen.tsx'
import { RunPanel } from '../RunPanel.tsx'
import { problemTitle } from '../States.tsx'
import { usePdfDocument } from './PdfPages.tsx'
import { useFailure, useRenderEnd } from './ReportScreen.tsx'
import '../export.css'
import './report.css'

export type AuditExportScreenProps = { jobId: string }

function kind(output: Output): 'docx' | 'pdf' {
  return output.name.toLowerCase().endsWith('.pdf') ? 'pdf' : 'docx'
}

export function AuditExportScreen({ jobId }: AuditExportScreenProps) {
  return (
    <JobProvider jobId={jobId}>
      <AuditExportView />
    </JobProvider>
  )
}

/** 7a for an audit, modelled on #41: the checks, the files of one run, one primary action.
 * Approving is the click on „Aprobă şi exportă”, bound to the listed final and the readiness
 * shown (§5.9). */
function AuditExportView() {
  const ctx = useJob()
  const { jobId } = ctx
  const report = useResource(jobKey(jobId, 'report'), () => auditReport.report(jobId))
  const approvals = useResource(jobKey(jobId, 'approvals'), () => api.approvals(jobId))
  const sections = useResource(jobKey(jobId, 'sections'), () => auditReport.sections(jobId))
  const visit = useResource(jobKey(jobId, 'visit'), () => api.visit(jobId))
  const generate = useAction()
  const approve = useAction()
  const save = useAction()
  const [exported, setExported] = useState<ExportReceipt | null>(null)
  useRenderEnd(jobId)

  const checks = ctx.checks.data
  const outputs = ctx.outputs.data ?? []
  const year = ctx.job.data?.year ?? ''
  const finalOk = checks?.readiness.final_ok ?? false
  const finalStale =
    checks?.readiness.blocking?.some((issue) => issue.code === 'final_stale') ?? false
  const firstBlocking = checks?.readiness.blocking?.[0]?.message
  const running = ctx.run?.state === 'running' || ctx.job.data?.state === 'running'
  const finalRun = report.data?.final ?? null
  const final = checks?.final
    ? (outputs.find((item) => item.id === checks.final?.output_id) ?? null)
    : null
  const draftRun = report.data?.draft ?? null
  const shownRun = final ? finalRun : draftRun?.state === 'ready' ? draftRun : null
  const files = final
    ? outputs.filter((item) => item.run_id === final.run_id)
    : shownRun
      ? outputs.filter((item) => item.run_id === shownRun.run_id)
      : []
  const draftDocx = outputs.find((item) => item.id === draftRun?.docx_output_id) ?? null
  const wordFile = final ?? draftDocx
  const pdf = usePdfDocument(
    jobId,
    final
      ? (files.find((item) => item.media_type === 'application/pdf')?.id ?? null)
      : (shownRun?.pdf_output_id ?? null),
  )
  const chapters = shownRun?.summary?.chapters.length ?? 0
  const photos = visit.data
    ? visit.data.thermal.length + visit.data.panels.reduce((sum, p) => sum + p.photos.length, 0)
    : 0
  const failedFinal = !running && finalRun?.state === 'failed'
  const failure = useFailure(jobId, finalRun?.run_id ?? null, failedFinal)
  const approval = final
    ? approvals.data?.find(
        (item) => item.output_id === final.id && item.readiness_hash === checks?.readiness_hash,
      )
    : undefined
  const refreshAll = () => {
    ctx.refresh('checks', 'outputs', 'job', 'report', 'approvals', 'sections')
  }

  const receipt =
    exported && exported.outputId === final?.id && exported.hash === checks?.readiness_hash
      ? exported.response
      : null
  const approvedAt = receipt?.approved_at ?? approval?.at
  let primary = null
  if (running) {
    primary = (
      <Button height={38} loading disabled>
        {final ? 'Aprobă şi exportă' : 'Generează versiunea finală'}
      </Button>
    )
  } else if (
    final &&
    !finalStale &&
    !receipt &&
    approvals.data &&
    (!approval || approval.exported_at === null)
  ) {
    primary = (
      <Button
        height={38}
        disabled={!finalOk || approve.pending || !checks}
        loading={approve.pending}
        onClick={() => {
          if (!checks) return
          void approve.run(
            async () => {
              const receipt = await exportPackage(jobId, final.id, checks.readiness_hash)
              if (!receipt) return
              setExported(receipt)
              refreshAll()
            },
            (problem) => {
              if (EXPORT_STALE.has(problem.code)) refreshAll()
            },
          )
        }}
      >
        Aprobă şi exportă
      </Button>
    )
  } else if (!final || finalStale) {
    primary = (
      <Button
        height={38}
        disabled={!canGenerateFinal(checks) || !checks || generate.pending || !ctx.job.data}
        loading={generate.pending}
        onClick={() => {
          const job = ctx.job.data
          if (!job) return
          void generate.run(
            async () => {
              const started = await auditReport.startFinal(jobId, job.revision)
              ctx.follow(started.run_id, started.stage)
              ctx.refresh('job', 'status')
            },
            (problem) => {
              if (EXPORT_STALE.has(problem.code)) refreshAll()
            },
          )
        }}
      >
        Generează versiunea finală
      </Button>
    )
  }
  const staleProblem = [approve.problem, generate.problem].find(
    (problem) => problem && EXPORT_STALE.has(problem.code),
  )
  const otherProblem = [approve.problem, generate.problem, save.problem].find(
    (problem) => problem && !EXPORT_STALE.has(problem.code),
  )
  const loadError = ctx.checks.error ?? report.error ?? ctx.outputs.error

  return (
    <Window>
      <AppSidebar activeJobId={jobId} working={ctx.job.data?.state === 'running'} />
      <section className="ema-content export">
        <div className="export__column">
          <a className="export__crumb" href={auditHref(jobId, 'structura')}>
            {`${clientName(ctx)} ${String(year)} · Audit energetic ${String(year)}`}
          </a>
          <h1 className="export__title">Predare</h1>
          {!checks && !loadError && <p className="report__loading">Se încarcă…</p>}
          {loadError !== undefined && !checks && (
            <FailureNotice
              title="Nu am putut încărca predarea"
              actions={
                <Button variant="secondary" height={30} onClick={refreshAll}>
                  Încearcă din nou
                </Button>
              }
            >
              {problemTitle(loadError)}
            </FailureNotice>
          )}
          {checks && (
            <p className="export__intro">
              {finalOk
                ? 'Raportul e complet pentru predare. Verifică o ultimă dată lucrurile de mai jos, apoi generează versiunea finală.'
                : 'Raportul nu e încă gata de predare. Rezolvă ce e marcat mai jos.'}
            </p>
          )}
          <div className="export__body">
            <DocThumb
              title={`Audit energetic ${String(year)}`}
              lines={[
                countRo(chapters, 'capitol', 'capitole'),
                ...(pdf.pages ? [countRo(pdf.pages, 'pagină', 'pagini')] : []),
              ]
                .join(' · ')
                .toUpperCase()}
              meta={shownRun?.ended_at ? `generat ${rel(shownRun.ended_at)}` : ''}
            />
            <div className="export__side">
              <div className="export__checks">
                <SectionKey>Înainte de depunere</SectionKey>
                {auditChecks(checks, sections.data, photos > 0).map((check, index) => (
                  <ExportCheck
                    key={check.label}
                    testId={`export-check-${String(index + 1)}`}
                    tone={check.tone}
                    label={check.label}
                    detail={check.detail}
                  />
                ))}
              </div>
              <div className="export__package">
                <SectionKey>Pachetul</SectionKey>
                <div className="export__files">
                  {files.map((file) => (
                    <PackageFile
                      key={file.id}
                      testId={`package-file-${file.id}`}
                      name={file.name}
                      size={formatBytes(file.size_bytes)}
                      kind={kind(file)}
                    />
                  ))}
                </div>
                {running && <RunPanel lines />}
              </div>
              <div className="export__actions">
                {approvedAt ? (
                  <Status tone="ok" mark="accepted">
                    {`Aprobat ${rel(approvedAt)}`}
                  </Status>
                ) : null}
                {primary}
                {wordFile && (
                  <Button
                    variant="secondary"
                    height={38}
                    loading={save.pending}
                    onClick={() => {
                      void save.run(() => download(jobId, wordFile))
                    }}
                  >
                    {final ? 'Descarcă doar Word' : 'Descarcă ciorna'}
                  </Button>
                )}
              </div>
              {!finalOk && !approval && firstBlocking && (
                <p className="export__blocked">{firstBlocking}</p>
              )}
              {receipt && (
                <div className="export__done">
                  <p>{`Fişierele finale sunt în ${receipt.folder}`}</p>
                  <ul>
                    {receipt.files.map((file) => (
                      <li key={file.path}>
                        {file.name} · {file.path}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {staleProblem && (
                <FailureNotice title={staleProblem.title} actions={null}>
                  Datele s-au schimbat de când ai deschis pagina. Verifică din nou.
                </FailureNotice>
              )}
              <ProblemNotice problem={otherProblem ?? null} />
              {failedFinal && !final && (
                <FailureNotice title={failure.message ?? 'Raportul nu s-a generat'} actions={null}>
                  {failure.message ? '' : failure.error}
                </FailureNotice>
              )}
            </div>
          </div>
        </div>
      </section>
    </Window>
  )
}
