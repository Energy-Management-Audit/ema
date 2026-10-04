import { useState } from 'react'
import { api } from '../../api/endpoints.ts'
import type { Field, Issue } from '../../api/types.ts'
import { sourceLabel } from '../../audit/sources.ts'
import { dataWarnings, sourceField } from '../../audit/warnings.ts'
import { useJob } from '../../state/job.tsx'
import { invalidate, useResource } from '../../state/resource.ts'
import { Button } from '../../ui/Button.tsx'
import { FailureNotice } from '../../ui/Feedback.tsx'
import { DataWarningRow, SourceButton } from '../../ui/Review.tsx'
import { SectionKey } from '../../ui/Surface.tsx'
import { problemTitle } from '../States.tsx'
import { EvidencePanel } from './EvidencePanel.tsx'

function WarningSource({ id, open, onOpen }: { id: string; open: boolean; onOpen: () => void }) {
  const evidence = useResource(`evidence/${id}`, () => api.evidence(id))
  const label = evidence.data
    ? sourceLabel(evidence.data, evidence.data.file_name ?? undefined)
    : 'Sursa'
  return (
    <SourceButton open={open} cell={evidence.data?.locator?.kind === 'cell'} onClick={onOpen}>
      <span className="ema-source-btn__text" title={label}>
        {label}
      </span>
    </SourceButton>
  )
}

function WarningSnippet({
  id,
  field,
  marked,
  close,
}: {
  id: string
  field: Field | undefined
  marked: string
  close: () => void
}) {
  const evidence = useResource(`evidence/${id}`, () => api.evidence(id))
  if (!field) return <span>Câmpul acestei surse nu mai există.</span>
  if (evidence.error && !evidence.data) {
    return (
      <FailureNotice
        title="Nu am putut încărca sursa"
        actions={
          <Button
            variant="secondary"
            height={30}
            disabled={evidence.loading}
            onClick={() => {
              invalidate(`evidence/${id}`)
            }}
          >
            Încearcă din nou
          </Button>
        }
      >
        {problemTitle(evidence.error)}
      </FailureNotice>
    )
  }
  if (!evidence.data) return <span>Se încarcă…</span>
  return <EvidencePanel field={field} evidence={evidence.data} close={close} marked={marked} />
}

/** 7f: the readiness data warnings of the audit, listed above the review queue. They never block
 * the report; each one opens both documents it compares. */
export function DataWarnings() {
  const ctx = useJob()
  const [opened, setOpened] = useState<string | null>(null)
  const warnings = dataWarnings(ctx.checks.data)
  if (!warnings.length) return null
  const fields = ctx.fields.data ?? []
  const row = (warning: Issue, index: number) => {
    const ids = warning.evidence_ids ?? []
    const openId = ids.find((id) => opened === `${String(index)}:${id}`)
    const toggle = (id: string) => {
      const key = `${String(index)}:${id}`
      setOpened(opened === key ? null : key)
    }
    return (
      <DataWarningRow
        key={`${warning.code}:${String(index)}`}
        label={fields.find((field) => field.id === warning.field_id)?.label ?? 'Date din dosar'}
        status="de verificat"
        message={warning.message}
        sources={ids.map((id) => (
          <WarningSource
            key={id}
            id={id}
            open={openId === id}
            onOpen={() => {
              toggle(id)
            }}
          />
        ))}
        snippet={
          openId ? (
            <WarningSnippet
              key={openId}
              id={openId}
              field={sourceField(fields, openId)}
              marked={warning.message}
              close={() => {
                setOpened(null)
              }}
            />
          ) : undefined
        }
      />
    )
  }
  return (
    <section className="audit-review-group" aria-label="Date de verificat">
      <SectionKey>DATE DE VERIFICAT · NU BLOCHEAZĂ RAPORTUL</SectionKey>
      {warnings.map(row)}
    </section>
  )
}
