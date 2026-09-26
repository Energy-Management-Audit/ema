import { useEffect, useState } from 'react'
import { api } from '../api/endpoints.ts'
import { jobHref } from '../app/route.ts'
import { navigate } from '../app/navigate.ts'
import { elapsed } from '../lib/format.ts'
import { useJob } from '../state/job.tsx'
import { Button } from '../ui/Button'
import { FailureNotice, ItemLine, ProgressBar } from '../ui/Feedback'
import { Card, CardHeader } from '../ui/Surface'
import { ProblemNotice, useAction } from './actions.tsx'
import { useGenerate, useGeneratePackage, useReadDocuments } from './JobHeader.tsx'
import { problemTitle } from './States.tsx'

const FAILED_TITLES: Record<string, string> = {
  piee_import: 'Documentele nu s-au putut citi',
  piee_generate: 'Generarea nu s-a încheiat',
  piee_word: 'Pachetul nu s-a generat',
}

function useElapsed(startedAt: string | null, running: boolean): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!running) return
    const timer = window.setInterval(() => {
      setNow(Date.now())
    }, 1000)
    return () => {
      window.clearInterval(timer)
    }
  }, [running])
  return startedAt ? (now - new Date(startedAt).getTime()) / 1000 : 0
}

/** R1 (3b/7b) while a run works; R2 when the latest run failed; „Oprit.” after a stop. */
export function RunPanel({ lines = false }: { lines?: boolean }) {
  const ctx = useJob()
  const run = ctx.run
  const running = run?.state === 'running'
  const seconds = useElapsed(run?.startedAt ?? null, running)
  const stop = useAction()
  const reader = useReadDocuments()
  const generate = useGenerate()
  const packager = useGeneratePackage()
  const latest = ctx.status.data?.runs.at(-1)
  if (running) {
    const progress = run.total > 0 ? Math.round((run.done / run.total) * 100) : 0
    const body = (
      <>
        <ItemLine state="working" dense detail={`${String(run.done)}/${String(run.total)}`}>
          {run.message}
        </ItemLine>
        {run.itemFailures > 0 && (
          <ItemLine state="failed" dense detail="">
            Un element nu s-a putut citi.
          </ItemLine>
        )}
        <ProgressBar value={progress} running />
        <Button
          variant="secondary"
          height={26}
          disabled={stop.pending}
          onClick={() => {
            void stop.run(async () => {
              await api.cancel(ctx.jobId)
              ctx.refresh('job', 'status')
            })
          }}
        >
          Opreşte
        </Button>
        <ProblemNotice problem={stop.problem} />
      </>
    )
    if (lines) {
      return (
        <div className="run-panel run-panel--lines" data-testid="run-panel">
          <span className="run-panel__title">Se lucrează</span>
          <span className="run-panel__time">{elapsed(seconds)}</span>
          {body}
        </div>
      )
    }
    return (
      <div className="run-panel" data-testid="run-panel">
        <Card>
          <CardHeader title="Se lucrează" count={elapsed(seconds)} />
          <div className="run-panel__body">{body}</div>
        </Card>
      </div>
    )
  }
  if (latest?.state === 'failed') {
    const retry =
      latest.stage === 'piee_import' ? reader : latest.stage === 'piee_word' ? packager : generate
    return (
      <div className="run-panel" data-testid="run-failed">
        <FailureNotice
          title={FAILED_TITLES[latest.stage] ?? 'Etapa a eşuat.'}
          actions={
            <div className="run-panel__exits">
              <Button
                height={28}
                loading={retry.pending}
                onClick={() => {
                  void retry.start()
                }}
              >
                Încearcă din nou
              </Button>
              <Button
                variant="secondary"
                height={28}
                onClick={() => {
                  navigate(jobHref(ctx.jobId, 'documente'))
                }}
              >
                Vezi documentele
              </Button>
            </div>
          }
        >
          {latest.error ?? ''}
        </FailureNotice>
        <ProblemNotice problem={retry.problem} />
      </div>
    )
  }
  if (latest?.state === 'cancelled') return <p className="run-panel__stopped">Oprit.</p>
  if (ctx.runError) return <p className="run-panel__stopped">{problemTitle(ctx.runError)}</p>
  return null
}
