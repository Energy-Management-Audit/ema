import { useRef, useState } from 'react'
import { createElement } from 'react'
import { api } from '../../api/endpoints.ts'
import { auditApi } from '../../api/audit.ts'
import { useJob } from '../../state/job.tsx'
import { Button } from '../../ui/Button.tsx'
import { Choice, Dialog } from '../../ui/Dialog.tsx'
import { FailureNotice } from '../../ui/Feedback.tsx'

type Target = 'dossier' | 'anexa' | 'measures' | 'meter' | 'thermal'

function slotFor(file: File, target: Target): string {
  if (target === 'anexa' || target === 'measures') return target
  if (target === 'thermal') return `visit/thermal/${file.name}`
  if (target === 'meter') {
    const parts = file.webkitRelativePath.split('/')
    return `visit/meter/${parts.length > 2 ? parts[1] : 'Tablou'}/${file.name}`
  }
  return `dossier/${file.name}`
}

export function AuditUploadDialog({
  onClose,
  dropped = [],
}: {
  onClose: () => void
  dropped?: File[]
}) {
  const ctx = useJob()
  const picker = useRef<HTMLInputElement>(null)
  const [target, setTarget] = useState<Target>('dossier')
  const [files, setFiles] = useState<File[]>(dropped)
  const [errors, setErrors] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const upload = async () => {
    if (!ctx.job.data || files.length === 0) return
    if ((target === 'anexa' || target === 'measures') && files.length > 1) {
      setErrors(['Alege un singur fişier pentru acest formular.'])
      return
    }
    setBusy(true)
    setErrors([])
    const failures: string[] = []
    for (const file of files) {
      try {
        const result = await api.upload(ctx.job.data.client_slug, file)
        await auditApi.putSlot(ctx.jobId, slotFor(file, target), result.sha)
      } catch (error) {
        failures.push(
          `${file.name}: ${error instanceof Error ? error.message : 'Cererea nu poate fi procesată.'}`,
        )
      }
    }
    ctx.refresh('job', 'documents', 'outline', 'checks')
    setErrors(failures)
    setBusy(false)
    if (failures.length === 0) onClose()
  }
  return (
    <Dialog
      title="Unde intră fişierele?"
      onClose={onClose}
      content={
        <div className="audit-upload-options">
          <Choice
            name="audit-upload"
            checked={target === 'dossier'}
            onSelect={() => {
              setTarget('dossier')
            }}
            title="Dosarul clientului"
            detail="Documentele primite de la client"
          />
          <Choice
            name="audit-upload"
            checked={target === 'anexa'}
            onSelect={() => {
              setTarget('anexa')
            }}
            title="Anexa 2–3"
            detail="Un fişier"
          />
          <Choice
            name="audit-upload"
            checked={target === 'measures'}
            onSelect={() => {
              setTarget('measures')
            }}
            title="Măsuri propuse"
            detail="Un fişier"
          />
          <Choice
            name="audit-upload"
            checked={target === 'meter' || target === 'thermal'}
            onSelect={() => {
              setTarget('meter')
            }}
            title="Fotografii din vizită"
            detail="Alege dosarul de fotografii"
          />
          {(target === 'meter' || target === 'thermal') && (
            <div className="audit-upload-options__sub">
              <Choice
                name="audit-visit"
                checked={target === 'meter'}
                onSelect={() => {
                  setTarget('meter')
                }}
                title="Contoare şi tablouri"
                detail="Fotografii grupate pe tablouri"
              />
              <Choice
                name="audit-visit"
                checked={target === 'thermal'}
                onSelect={() => {
                  setTarget('thermal')
                }}
                title="Imagini termografice"
                detail="Fotografii termice"
              />
            </div>
          )}
          <Button variant="secondary" height={30} onClick={() => picker.current?.click()}>
            Alege fişierele
          </Button>
          {createElement('input', {
            ref: picker,
            hidden: true,
            type: 'file',
            multiple: target !== 'anexa' && target !== 'measures',
            webkitdirectory: target === 'meter' || target === 'thermal' ? '' : undefined,
            onChange: (event: React.ChangeEvent<HTMLInputElement>) => {
              setFiles(Array.from(event.target.files ?? []))
            },
          })}
          {files.length > 0 && <span>{files.map((file) => file.name).join(', ')}</span>}
          {errors.map((error) => (
            <FailureNotice key={error} title="Nu am putut adăuga fişierul" actions={null}>
              {error}
            </FailureNotice>
          ))}
        </div>
      }
      actions={
        <>
          <Button variant="secondary" height={36} onClick={onClose}>
            Renunţă
          </Button>
          <Button
            height={36}
            disabled={!files.length || busy}
            loading={busy}
            onClick={() => void upload()}
          >
            Adaugă documente
          </Button>
        </>
      }
    >
      Selectează locul în care intră fişierele.
    </Dialog>
  )
}
