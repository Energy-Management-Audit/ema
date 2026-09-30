import { useState } from 'react'
import { api } from '../api/endpoints.ts'
import type { Evidence, Field } from '../api/types.ts'
import { formatDate, withUnit } from '../lib/format.ts'
import { cellReference, evidenceChip, fieldLabel } from '../piee/labels.ts'
import { useJob } from '../state/job.tsx'
import { useResource } from '../state/resource.ts'
import { Button } from '../ui/Button'
import { SourceChip } from '../ui/Chip'
import { SectionKey } from '../ui/Surface'

export function useEvidence(id: string | null | undefined) {
  return useResource<Evidence>(id ? `evidence:${id}` : null, () => api.evidence(id ?? ''))
}

/** The source chip of one evidence record (M5): document cell, calculated or manual. */
export function EvidenceChip({ id, onClick }: { id: string; onClick?: () => void }) {
  const evidence = useEvidence(id)
  if (!evidence.data) {
    return (
      <SourceChip kind="document" onClick={onClick}>
        …
      </SourceChip>
    )
  }
  const chip = evidenceChip(evidence.data)
  return (
    <SourceChip kind={chip.kind} onClick={onClick}>
      {chip.text}
    </SourceChip>
  )
}

export function fieldValue(field: Field): string {
  if (field.value === null || field.value === undefined) return '—'
  const text =
    typeof field.value === 'string' || typeof field.value === 'number' ? String(field.value) : '—'
  return field.value_type === 'number' ? withUnit(text, field.unit) : text
}

function FileName({ name }: { name: string | null | undefined }) {
  return <span>{name ?? ''}</span>
}

function Inputs({ inputs }: { inputs: string[] }) {
  const { fields, job } = useJob()
  const byKey = new Map((fields.data ?? []).map((field) => [field.key, field]))
  return (
    <div className="evidence-inputs">
      {inputs.map((input) => {
        const field = byKey.get(input)
        if (!field) {
          return (
            <span key={input} className="evidence-inputs__raw">
              {input}
            </span>
          )
        }
        return (
          <div key={input} className="evidence-inputs__row">
            <span>{fieldLabel(field.key, field.label, job.data?.year ?? null)}</span>
            <span className="ema-figures">{fieldValue(field)}</span>
            {field.evidence?.[0] && <EvidenceChip id={field.evidence[0]} />}
          </div>
        )
      })}
    </div>
  )
}

/** What a chip opens (M5): the cell and file it came from, or the inputs of a calculation. */
export function EvidenceDetail({ id }: { id: string }) {
  const evidence = useEvidence(id)
  const [inputs, setInputs] = useState(false)
  const data = evidence.data
  if (!data) return <div className="evidence-detail" data-testid="evidence-detail" />
  if (data.method === 'calc' && data.derivation) {
    const derivation = data.derivation
    return (
      <div className="evidence-detail" data-testid="evidence-detail">
        <div className="evidence-detail__line">
          <span>{`calculat · ${String(derivation.inputs.length)} intrări`}</span>
          <Button
            variant="secondary"
            height={28}
            aria-expanded={inputs}
            onClick={() => {
              setInputs(!inputs)
            }}
          >
            Vezi intrările
          </Button>
        </div>
        {inputs && <Inputs inputs={derivation.inputs} />}
        <span className="evidence-detail__mono">{`formula ${derivation.formula_id}`}</span>
        <span className="evidence-detail__mono">{`factori ${derivation.factor_version}`}</span>
      </div>
    )
  }
  if (data.locator?.kind === 'cell') {
    return (
      <div className="evidence-detail" data-testid="evidence-detail">
        <SectionKey>Celula din document</SectionKey>
        <span className="evidence-detail__mono">{cellReference(data)}</span>
        {data.file_sha && <FileName name={data.file_name} />}
        <span className="evidence-detail__muted">{`citit ${formatDate(data.retrieved_at)}`}</span>
      </div>
    )
  }
  return (
    <div className="evidence-detail" data-testid="evidence-detail">
      <span className="evidence-detail__muted">{evidenceChip(data).text}</span>
    </div>
  )
}
