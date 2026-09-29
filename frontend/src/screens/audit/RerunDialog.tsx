import { useState } from 'react'
import { auditApi } from '../../api/audit.ts'
import { plural } from '../../lib/plural.ts'
import { useJob } from '../../state/job.tsx'
import { Button } from '../../ui/Button.tsx'
import { Dialog } from '../../ui/Dialog.tsx'

/** 7c: design handoff screen component. */
export function RerunDialog({
  stage,
  count,
  onClose,
}: {
  stage: 'intake' | 'read'
  count: number
  onClose: () => void
}) {
  const ctx = useJob()
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const start = async () => {
    if (!ctx.job.data) return
    setBusy(true)
    setProblem(null)
    try {
      const result = await auditApi.startStage(ctx.jobId, stage, ctx.job.data.revision)
      ctx.follow(result.run_id, stage)
      ctx.refresh('job', 'status', 'documents', 'outline')
      onClose()
    } catch (error) {
      setProblem(error instanceof Error ? error.message : 'Cererea nu poate fi procesată.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <Dialog
      title="Reiei extragerea?"
      onClose={onClose}
      actions={
        <>
          <Button variant="secondary" height={36} onClick={onClose}>
            Renunţă
          </Button>
          <Button height={36} disabled={busy} loading={busy} onClick={() => void start()}>
            Reia extragerea
          </Button>
        </>
      }
    >
      Ai acceptat deja {plural(count, 'câmp', 'câmpuri')}. Cele care ies la fel rămân acceptate; o
      valoare nouă diferită revine la revizuire, cu vechea valoare alături. Ce ai scris tu nu se
      schimbă.
      {problem && <span role="alert">{problem}</span>}
    </Dialog>
  )
}
