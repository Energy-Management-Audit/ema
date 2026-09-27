import { useState } from 'react'
import { X } from 'lucide-react'
import { api } from '../../api/endpoints.ts'
import type { Field } from '../../api/types.ts'
import { auditApi } from '../../api/audit.ts'
import { sourceLabel } from '../../audit/sources.ts'
import { scalar } from '../../audit/review.ts'
import { formatNumber, rel } from '../../lib/format.ts'
import { useJob } from '../../state/job.tsx'
import { invalidate } from '../../state/resource.ts'
import { useResource } from '../../state/resource.ts'
import { Button, IconButton } from '../../ui/Button.tsx'
import { Status } from '../../ui/Chip.tsx'
import { FieldReviewRow, ReviewValue, SourceButton } from '../../ui/Review.tsx'
import { ValueEditor } from '../ValueEditor.tsx'
import { EvidencePanel } from './EvidencePanel.tsx'

export function AuditFieldRow({
  field,
  open,
  onOpen,
}: {
  field: Field
  open: boolean
  onOpen: () => void
}) {
  const ctx = useJob()
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const evidenceId = field.evidence?.[0]
  const evidence = useResource(evidenceId ? `evidence/${evidenceId}` : null, () =>
    api.evidence(evidenceId ?? ''),
  )
  const fileName = useResource(
    evidence.data?.file_sha && ctx.job.data
      ? `file/${ctx.job.data.client_slug}/${evidence.data.file_sha}`
      : null,
    () => api.fileVersions(ctx.job.data?.client_slug ?? '', evidence.data?.file_sha ?? ''),
  )
  const last = ctx.log.data?.filter((item) => item.field_id === field.id && !item.undone_by).at(-1)
  const status =
    field.presence !== 'found'
      ? 'lipseşte'
      : field.review === 'accepted'
        ? `acceptat ${last ? rel(last.at) : ''}`
        : field.review === 'corrected'
          ? 'scris de tine'
          : field.review === 'rejected'
            ? `respins ${last ? rel(last.at) : ''}`
            : field.state === 'enriched'
              ? 'din online · de confirmat'
              : field.state === 'calculated'
                ? 'calculat · se actualizează singur'
                : field.confidence === 'exact'
                  ? 'potrivire exactă'
                  : field.confidence === 'partial'
                    ? 'potrivire parţială'
                    : field.confidence === 'conflict'
                      ? 'două valori diferite'
                      : 'lipseşte'
  const act = async (action: 'accept' | 'reject' | 'undo') => {
    setBusy(true)
    setProblem(null)
    try {
      if (action === 'undo') {
        if (last) await api.undo(ctx.jobId, last.id)
      } else await auditApi.decide(ctx.jobId, field, action)
      ctx.refresh('fields', 'log', 'outline', 'checks')
      invalidate('overview')
    } catch (error) {
      setProblem(error instanceof Error ? error.message : 'Cererea nu poate fi procesată.')
    } finally {
      setBusy(false)
    }
  }
  const source = evidence.data ? (
    <SourceButton open={open} cell={evidence.data.locator?.kind === 'cell'} onClick={onOpen}>
      {sourceLabel(evidence.data, fileName.data?.[0]?.name)}
    </SourceButton>
  ) : evidenceId ? (
    <SourceButton open={open} onClick={onOpen}>
      Sursa
    </SourceButton>
  ) : null
  const display =
    field.value === null || field.value === undefined
      ? '—'
      : field.value_type === 'number'
        ? formatNumber(scalar(field.value), field.unit)
        : scalar(field.value)
  const previous =
    last && field.review === 'corrected' && last.before.value != null
      ? field.value_type === 'number'
        ? formatNumber(scalar(last.before.value), field.unit)
        : scalar(last.before.value)
      : undefined
  const actions =
    field.presence !== 'found' ? (
      <Button
        variant="secondary"
        height={30}
        onClick={() => {
          setEditing(true)
        }}
      >
        Scrie valoarea
      </Button>
    ) : field.review === 'pending' ? (
      <>
        <Button
          variant="olive"
          height={30}
          disabled={busy || field.confidence === 'conflict' || field.needs_confirmation}
          onClick={() => void act('accept')}
        >
          Acceptă
        </Button>
        <IconButton
          icon={X}
          label="Respinge"
          size={30}
          disabled={busy}
          onClick={() => void act('reject')}
        />
      </>
    ) : (
      <Button variant="soft" height={30} disabled={busy || !last} onClick={() => void act('undo')}>
        Anulează
      </Button>
    )
  return (
    <>
      <FieldReviewRow
        label={field.label}
        status={
          <Status
            tone={
              field.review === 'accepted' || field.review === 'corrected'
                ? 'ok'
                : field.review === 'rejected'
                  ? 'err'
                  : field.confidence === 'exact'
                    ? 'muted'
                    : 'warn'
            }
          >
            {status}
          </Status>
        }
        value={
          <ReviewValue previous={previous}>
            {display}
            {field.unit ? ` ${field.unit}` : ''}
          </ReviewValue>
        }
        source={source}
        actions={actions}
        snippet={
          open ? (
            evidence.data ? (
              <EvidencePanel field={field} evidence={evidence.data} close={onOpen} />
            ) : (
              <span>Se încarcă…</span>
            )
          ) : undefined
        }
      />
      {editing && (
        <ValueEditor
          field={field}
          autoFocus
          onDone={() => {
            setEditing(false)
          }}
        />
      )}
      {problem && (
        <p className="audit-error" role="alert">
          {problem}
        </p>
      )}
    </>
  )
}
