import { useRef, useState } from 'react'
import { FileText, Image, Sheet } from 'lucide-react'
import { api } from '../../api/endpoints.ts'
import type { DocFile } from '../../api/audit-types.ts'
import { auditApi } from '../../api/audit.ts'
import { formatBytes } from '../../lib/format.ts'
import { useJob } from '../../state/job.tsx'
import { invalidate } from '../../state/resource.ts'
import { Button } from '../../ui/Button.tsx'
import { FailureNotice } from '../../ui/Feedback.tsx'
import { Icon } from '../../ui/Icon.tsx'

export function DocumentRow({
  file,
  label,
  ocr,
}: {
  file: DocFile | null
  label?: string
  ocr?: boolean
}) {
  const ctx = useJob()
  const picker = useRef<HTMLInputElement>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  if (!file)
    return (
      <div className="audit-doc-row">
        <strong>{label}</strong>
        <span>lipseşte</span>
      </div>
    )
  const issue = ['failed', 'protected', 'needs_conversion', 'scanned'].includes(file.status)
  const summary = file.item_text ?? (issue ? file.reason : null)
  const remove = async () => {
    if (!ctx.job.data) return
    setBusy(true)
    setProblem(null)
    try {
      await api.removeVersion(ctx.jobId, file.slot, file.version, file.slot_revision)
      ctx.refresh('job', 'documents', 'checks')
      invalidate('overview')
    } catch (error) {
      setProblem(error instanceof Error ? error.message : 'Cererea nu poate fi procesată.')
    } finally {
      setBusy(false)
    }
  }
  const replace = async (newFile: File) => {
    if (!ctx.job.data) return
    setBusy(true)
    setProblem(null)
    try {
      const uploaded = await api.upload(ctx.job.data.client_slug, newFile)
      await auditApi.putSlot(ctx.jobId, file.slot, uploaded.sha)
      ctx.refresh('job', 'documents', 'checks')
    } catch (error) {
      setProblem(error instanceof Error ? error.message : 'Cererea nu poate fi procesată.')
    } finally {
      setBusy(false)
    }
  }
  const icon = file.kind.includes('xls') ? Sheet : file.kind.includes('image') ? Image : FileText
  return (
    <div className="audit-doc-row" data-status={file.status}>
      <Icon icon={icon} size={17} stroke={1.6} />
      <div className="audit-doc-row__body">
        <strong>{label ?? file.name}</strong>
        <small>
          {file.kind.toUpperCase()} · {formatBytes(file.size_bytes)}
          {file.item !== null ? ` · ${String(file.item)}.` : ' · neclasificat'}
        </small>
        {issue && (
          <FailureNotice
            title={
              file.status === 'protected'
                ? 'Protejat cu parolă'
                : file.status === 'scanned'
                  ? 'Text scanat'
                  : file.status === 'needs_conversion'
                    ? 'Fişier .doc'
                    : `${file.name} nu a putut fi citit`
            }
            actions={
              <>
                {file.status === 'failed' && (
                  <Button
                    variant="secondary"
                    height={28}
                    disabled={busy}
                    onClick={() => picker.current?.click()}
                  >
                    Reîncarcă
                  </Button>
                )}
                <Button
                  variant="secondary"
                  height={28}
                  disabled={busy}
                  onClick={() => void remove()}
                >
                  Scoate
                </Button>
              </>
            }
          >
            {file.status === 'protected'
              ? 'Protejat cu parolă — Ema nu l-a putut deschide. Nu intră în audit.'
              : file.status === 'scanned'
                ? ocr
                  ? 'Text scanat — Ema îl citeşte cu OCR la extragere. Originalul rămâne neatins.'
                  : 'Text scanat — nu s-a putut citi nimic. Originalul rămâne neatins.'
                : file.status === 'needs_conversion'
                  ? 'Fişier .doc — Word nu l-a putut converti. Originalul rămâne neatins.'
                  : (file.reason ?? 'Fişierul nu a putut fi citit.')}
          </FailureNotice>
        )}
        {problem && (
          <p className="audit-error" role="alert">
            {problem}
          </p>
        )}
      </div>
      <span className={`audit-doc-row__summary${issue ? ' audit-doc-row__summary--warn' : ''}`}>
        {summary ?? '—'}
      </span>
      <span className={`audit-doc-row__status audit-doc-row__status--${file.status}`}>
        {file.status === 'read'
          ? 'CITIT'
          : file.status === 'reading'
            ? 'se citeşte…'
            : file.status === 'unread'
              ? 'necitit'
              : file.status === 'failed'
                ? 'eşuat'
                : file.status === 'protected'
                  ? 'protejat'
                  : file.status === 'scanned'
                    ? 'scanat'
                    : 'conversie necesară'}
      </span>
      <input
        ref={picker}
        type="file"
        hidden
        onChange={(event) => {
          const selected = event.target.files?.[0]
          if (selected) void replace(selected)
        }}
      />
    </div>
  )
}
