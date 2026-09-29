import { useState } from 'react'
import { api } from '../api/endpoints.ts'
import type { Output } from '../api/types.ts'
import { jobHref } from '../app/route.ts'
import { formatBytes, rel } from '../lib/format.ts'
import { blockingIssues, draftDocuments, exportChecks } from '../piee/readiness.ts'
import { useJob } from '../state/job.tsx'
import { jobKey, useResource } from '../state/resource.ts'
import { Button } from '../ui/Button'
import { Status } from '../ui/Chip'
import { FailureNotice } from '../ui/Feedback'
import { DocThumb, ExportCheck, PackageFile } from '../ui/Package'
import { SectionKey } from '../ui/Surface'
import {
  ProblemNotice,
  STALE_CODES,
  download,
  exportPackage,
  type ExportReceipt,
  useAction,
} from './actions.tsx'
import { useGeneratePackage } from './JobHeader.tsx'
import { clientName } from './JobScreen.tsx'
import { RunPanel } from './RunPanel.tsx'
import './export.css'

function kind(output: Output): 'docx' | 'xlsx' | 'pdf' {
  const name = output.name.toLowerCase()
  return name.endsWith('.pdf') ? 'pdf' : name.endsWith('.xlsx') ? 'xlsx' : 'docx'
}

const APPROVE_STALE = new Set(['hash_mismatch', 'output_stale', 'not_ready', 'job_running'])

/** S6 (7a, Q1 A): the checks, the package as real files, one primary action. Approving is the
 * click on „Aprobă şi exportă”, bound to the listed final and the readiness shown (§5.9). */
export function ExportScreen() {
  const ctx = useJob()
  const approvals = useResource(jobKey(ctx.jobId, 'approvals'), () => api.approvals(ctx.jobId))
  const packager = useGeneratePackage()
  const approve = useAction()
  const word = useAction()
  const [exported, setExported] = useState<ExportReceipt | null>(null)
  const checks = ctx.checks.data
  const summary = ctx.summary.data
  const outputs = ctx.outputs.data ?? []
  const year = ctx.job.data?.year ?? ''
  const finalOk = checks?.readiness.final_ok ?? false
  const firstBlocking = blockingIssues(checks)[0]?.message
  const running = ctx.run?.state === 'running' || ctx.job.data?.state === 'running'
  const final = checks?.final
    ? (outputs.find((item) => item.id === checks.final?.output_id) ?? null)
    : null
  const draft = draftDocuments(outputs).at(-1)
  const shown = final ?? draft
  const files = final
    ? outputs.filter((item) => item.run_id === final.run_id)
    : draft
      ? outputs.filter((item) => item.run_id === draft.run_id)
      : []
  const approval = final
    ? approvals.data?.find(
        (item) => item.output_id === final.id && item.readiness_hash === checks?.readiness_hash,
      )
    : undefined
  const refreshAfterApprove = () => {
    ctx.refresh('checks', 'outputs', 'job')
    ctx.refresh('approvals')
  }
  const wordFile = final ?? draft
  const receipt =
    exported && exported.outputId === final?.id && exported.hash === checks?.readiness_hash
      ? exported.response
      : null
  const approvedAt = receipt?.approved_at ?? approval?.at
  let primary = null
  if (running) {
    primary = (
      <Button height={38} loading disabled>
        {final ? 'Aprobă şi exportă' : 'Generează pachetul'}
      </Button>
    )
  } else if (final && !receipt) {
    primary = (
      <Button
        height={38}
        disabled={!finalOk || approve.pending || !checks}
        loading={approve.pending}
        onClick={() => {
          if (!checks) return
          void approve.run(
            async () => {
              const receipt = await exportPackage(ctx.jobId, final.id, checks.readiness_hash)
              if (!receipt) return
              setExported(receipt)
              refreshAfterApprove()
            },
            (problem) => {
              if (APPROVE_STALE.has(problem.code)) refreshAfterApprove()
            },
          )
        }}
      >
        Aprobă şi exportă
      </Button>
    )
  } else if (!final) {
    primary = (
      <Button
        height={38}
        disabled={!finalOk || packager.pending}
        loading={packager.pending}
        onClick={() => {
          void packager.start()
        }}
      >
        Generează pachetul
      </Button>
    )
  }
  return (
    <section className="ema-content export">
      <div className="export__column">
        <a className="export__crumb" href={jobHref(ctx.jobId, 'date')}>
          {`${clientName(ctx)} ${String(year)} · PIEE ${String(year)}`}
        </a>
        <h1 className="export__title">Predare</h1>
        <p className="export__intro">
          {finalOk
            ? 'Programul e complet pentru depunere. Verifică o ultimă dată cele patru lucruri de mai jos, apoi generează pachetul.'
            : 'Programul nu e încă gata de depunere. Rezolvă ce e marcat mai jos.'}
        </p>
        <div className="export__body">
          <DocThumb
            title={`PIEE ${String(year)}`}
            lines={`${String(summary?.measures_total ?? 0)} MĂSURI`}
            meta={shown?.created_at ? `generat ${rel(shown.created_at)}` : ''}
          />
          <div className="export__side">
            <div className="export__checks">
              <SectionKey>Înainte de depunere</SectionKey>
              {exportChecks(checks, summary).map((check, index) => (
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
                  loading={word.pending}
                  onClick={() => {
                    void word.run(
                      () => download(ctx.jobId, wordFile),
                      (problem) => {
                        if (STALE_CODES.has(problem.code)) ctx.refresh('job', 'checks', 'outputs')
                      },
                    )
                  }}
                >
                  Descarcă doar Word
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
            {approve.problem &&
              (APPROVE_STALE.has(approve.problem.code) ? (
                <FailureNotice title={approve.problem.title} actions={null}>
                  Datele s-au schimbat de când ai deschis pagina. Verifică din nou.
                </FailureNotice>
              ) : (
                <ProblemNotice problem={approve.problem} />
              ))}
            <ProblemNotice problem={packager.problem ?? word.problem} />
            {!running && <RunPanel />}
          </div>
        </div>
      </div>
    </section>
  )
}
