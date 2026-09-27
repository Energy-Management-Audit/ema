import { useEffect, useState } from 'react'
import type { JobOverview } from '../../api/types.ts'
import { ApiProblem } from '../../api/client.ts'
import { api } from '../../api/endpoints.ts'
import { jobLabel } from '../../app/sidebar.ts'
import { roCount } from '../../clients/plural.ts'
import { invalidate } from '../../state/resource.ts'
import { Button } from '../../ui/Button.tsx'
import { Dialog } from '../../ui/Dialog.tsx'
import { FailureNotice } from '../../ui/Feedback.tsx'

export function DeleteJobDialog({
  job,
  clientName,
  onClose,
}: {
  job: JobOverview
  clientName: string
  onClose: () => void
}) {
  const [counts, setCounts] = useState<{ files: number; fields: number } | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    void Promise.all([api.slots(job.id), api.fields(job.id)]).then(
      ([slots, fields]) => {
        setCounts({ files: slots.length, fields: fields.length })
      },
      (error: unknown) => {
        setProblem(error instanceof ApiProblem ? error.title : 'Cererea nu poate fi procesată.')
      },
    )
  }, [job.id])
  async function remove() {
    setBusy(true)
    try {
      await api.deleteJob(job.id, job.revision)
      invalidate('overview')
      onClose()
    } catch (error) {
      if (error instanceof ApiProblem && error.code === 'stale_revision') invalidate('overview')
      setProblem(error instanceof ApiProblem ? error.title : 'Cererea nu poate fi procesată.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <Dialog
      title={`Ştergi „${jobLabel(job)} · ${clientName}”?`}
      onClose={onClose}
      actions={
        <>
          <Button variant="secondary" height={36} onClick={onClose}>
            Renunţă
          </Button>
          <Button
            variant="destructive"
            height={36}
            disabled={!counts || busy || problem != null}
            loading={busy}
            onClick={() => {
              void remove()
            }}
          >
            Şterge lucrarea
          </Button>
        </>
      }
      content={
        problem && (
          <FailureNotice title={problem} actions={null}>
            {problem}
          </FailureNotice>
        )
      }
    >
      {counts
        ? `Se şterg ${roCount(counts.files, 'fişier încărcat', 'fişiere încărcate')} şi ${roCount(counts.fields, 'câmp extras', 'câmpuri extrase')} din ele. Celelalte lucrări ale clientului rămân neatinse. Acţiunea nu poate fi anulată.`
        : 'Se numără fişierele…'}
    </Dialog>
  )
}
