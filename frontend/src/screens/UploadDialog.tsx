import { useState } from 'react'
import { api } from '../api/endpoints.ts'
import { formatBytes } from '../lib/format.ts'
import { useJob } from '../state/job.tsx'
import { Button } from '../ui/Button'
import { Choice, Dialog } from '../ui/Dialog'
import { ProblemNotice, useAction } from './actions.tsx'
import { SLOT_TITLES } from './SlotRow.tsx'

/** DG2: pick one file, say which slot it fills, then upload and bind it. */
export function UploadDialog({ file, onClose }: { file: File; onClose: () => void }) {
  const ctx = useJob()
  const [slot, setSlot] = useState<string | null>(null)
  const action = useAction()
  const client = ctx.job.data?.client_slug ?? ''
  const confirm = () =>
    action.run(async () => {
      if (!slot) return
      const stored = await api.upload(client, file)
      if (slot === 'prelucrare') await api.bindPrelucrare(ctx.jobId, stored.sha)
      else await api.putSlot(ctx.jobId, slot, stored.sha)
      ctx.refresh('slots', 'prelucrare', 'checks', 'job')
      onClose()
    })
  return (
    <Dialog
      title="Unde intră fişierul?"
      onClose={onClose}
      content={
        <div className="upload-choices">
          {Object.entries(SLOT_TITLES).map(([name, title]) => (
            <Choice
              key={name}
              name="upload-slot"
              checked={slot === name}
              onSelect={() => {
                setSlot(name)
              }}
              title={title}
              detail=""
            />
          ))}
          <ProblemNotice problem={action.problem} />
        </div>
      }
      actions={
        <>
          <Button variant="secondary" height={36} onClick={onClose}>
            Renunţă
          </Button>
          <Button
            height={36}
            disabled={!slot || action.pending}
            loading={action.pending}
            onClick={() => {
              void confirm()
            }}
          >
            Adaugă
          </Button>
        </>
      }
    >
      {`${file.name} · ${formatBytes(file.size)}`}
    </Dialog>
  )
}
