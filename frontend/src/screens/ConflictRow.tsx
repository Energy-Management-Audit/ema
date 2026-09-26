import { useEffect, useRef, useState } from 'react'
import { api } from '../api/endpoints.ts'
import type { Candidate, Field } from '../api/types.ts'
import { formatNumber } from '../lib/format.ts'
import { docLabel, fieldLabel } from '../piee/labels.ts'
import { useJob } from '../state/job.tsx'
import { Button } from '../ui/Button'
import { Status } from '../ui/Chip'
import { FieldReviewRow, ReviewValue, SourceButton } from '../ui/Review'
import { SectionKey } from '../ui/Surface'
import { ProblemNotice, STALE_CODES, useAction } from './actions.tsx'
import { EvidenceChip, EvidenceDetail, useEvidence } from './EvidenceDetail.tsx'
import { DECISION_KEYS } from './JournalEntries.tsx'
import { ValueEditor } from './ValueEditor.tsx'

export function shownValue(field: Field, value: unknown): string {
  const text = typeof value === 'string' || typeof value === 'number' ? String(value) : ''
  return field.value_type === 'number' ? formatNumber(text, field.unit) : text
}

function OtherSource({ candidate, field }: { candidate: Candidate; field: Field }) {
  const evidence = useEvidence(candidate.evidence[0])
  const method = evidence.data?.method
  const source = method === 'calc' ? 'Calculul' : method ? docLabel(method) : '…'
  return <>{`${source} spune ${shownValue(field, candidate.value)}`}</>
}

function Alternative({ field, candidate }: { field: Field; candidate: Candidate }) {
  const ctx = useJob()
  const [detail, setDetail] = useState(false)
  const choose = useAction()
  const value = shownValue(field, candidate.value)
  return (
    <div className="conflict-alternative">
      <div className="conflict-alternative__line">
        <span className="conflict-alternative__value">{value}</span>
        {candidate.evidence[0] && (
          <EvidenceChip
            id={candidate.evidence[0]}
            onClick={() => {
              setDetail(!detail)
            }}
          />
        )}
        <Button
          variant="secondary"
          height={28}
          loading={choose.pending}
          disabled={choose.pending}
          onClick={() => {
            void choose.run(
              async () => {
                await api.choose(ctx.jobId, field.id, candidate.id, field.revision ?? 1)
                ctx.refresh(...DECISION_KEYS)
              },
              (problem) => {
                if (STALE_CODES.has(problem.code)) ctx.refresh(...DECISION_KEYS)
              },
            )
          }}
        >
          {`Foloseşte ${value}`}
        </Button>
      </div>
      {detail && candidate.evidence[0] && <EvidenceDetail id={candidate.evidence[0]} />}
      <ProblemNotice problem={choose.problem} />
    </div>
  )
}

/** A conflict (3c FieldReviewRow): two sources disagree; choosing one is a Jurnal decision. */
export function ConflictRow({ field, focus }: { field: Field; focus: boolean }) {
  const { job } = useJob()
  const [open, setOpen] = useState(focus)
  const [writing, setWriting] = useState(false)
  const row = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (focus) row.current?.scrollIntoView({ block: 'center' })
  }, [focus])
  const alternatives = field.alternatives ?? []
  const other = alternatives.find((item) => String(item.value) !== String(field.value))
  return (
    <div ref={row} data-testid={`conflict-row-${field.id}`}>
      <FieldReviewRow
        label={fieldLabel(field.key, field.label, job.data?.year ?? null)}
        status={<Status tone="warn">două valori diferite</Status>}
        value={<ReviewValue>{shownValue(field, field.value)}</ReviewValue>}
        note={other ? <OtherSource candidate={other} field={field} /> : undefined}
        source={
          <SourceButton
            cell
            open={open}
            onClick={() => {
              setOpen(!open)
            }}
          >
            {`${String(alternatives.length)} surse`}
          </SourceButton>
        }
        snippet={
          open ? (
            <div className="conflict-open">
              <div className="conflict-open__alternatives">
                {alternatives.map((candidate) => (
                  <Alternative key={candidate.id} field={field} candidate={candidate} />
                ))}
              </div>
              <div className="conflict-open__why">
                <SectionKey>De ce e marcat nesigur</SectionKey>
                <p>Sursele dau valori diferite. Decizia intră în Jurnal şi se poate anula.</p>
                {writing ? (
                  <ValueEditor
                    field={field}
                    autoFocus
                    onDone={() => {
                      setWriting(false)
                    }}
                  />
                ) : (
                  <Button
                    variant="secondary"
                    height={28}
                    onClick={() => {
                      setWriting(true)
                    }}
                  >
                    Scrie altă valoare
                  </Button>
                )}
              </div>
            </div>
          ) : undefined
        }
      />
    </div>
  )
}
