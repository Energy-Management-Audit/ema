import { useState } from 'react'
import type { Candidate, Field } from '../api/types.ts'
import { jobHref } from '../app/route.ts'
import { formatNumber } from '../lib/format.ts'
import { carrierTables } from '../piee/dataset.ts'
import { docLabel, fieldLabel } from '../piee/labels.ts'
import { blockingIssues, hasIssue } from '../piee/readiness.ts'
import { useJob } from '../state/job.tsx'
import { Button } from '../ui/Button'
import { EmaWidget, EmptyState } from '../ui/Feedback'
import { SectionKey } from '../ui/Surface'
import { ProblemNotice } from './actions.tsx'
import { useMissing } from './BlockingPanel.tsx'
import { CarrierTable } from './CarrierTable.tsx'
import { ConflictRow } from './ConflictRow.tsx'
import { useEvidence } from './EvidenceDetail.tsx'
import { useReadDocuments } from './JobHeader.tsx'
import { MissingRow } from './MissingRow.tsx'
import { ValueEditor } from './ValueEditor.tsx'
import './data.css'

function Phrase({ field, candidate }: { field: Field; candidate: Candidate }) {
  const evidence = useEvidence(candidate.evidence[0])
  const data = evidence.data
  const value = `${formatNumber(String(candidate.value), field.unit)} ${field.unit ?? ''}`.trim()
  if (!data) return <>{value}</>
  const annual =
    data.method === 'anexa' &&
    (field.key === 'annual.total_tep' || /date anuale/i.test(data.locator?.sheet ?? ''))
  const phrase =
    data.method === 'calc'
      ? 'calculat'
      : annual
        ? 'în „Date anuale”'
        : `în ${docLabel(data.method)}`
  return <>{`${value} ${phrase}`}</>
}

function Banner({ conflicts, year }: { conflicts: Field[]; year: number | null }) {
  const { jobId } = useJob()
  const first = conflicts.at(0)
  if (!first) return null
  const onAnnual = conflicts.some((field) => field.key === 'annual.total_tep')
  const keyYear = first.key.startsWith('carrier.') ? first.key.split('.')[2] : null
  const shownYear = keyYear ?? (year === null ? '' : String(year - 1))
  const alternatives = first.alternatives ?? []
  return (
    <EmaWidget
      title={
        onAnnual
          ? 'Totalul anual nu se potriveşte cu Anexa 2–3'
          : `${String(conflicts.length)} valori diferite între surse`
      }
      actions={
        <a
          className="ema-btn ema-btn--primary ema-btn--h32"
          href={jobHref(jobId, 'date', first.id)}
        >
          Du-mă la conflict
        </a>
      }
    >
      {`${shownYear}: `}
      {alternatives.map((candidate, index) => (
        <span key={candidate.id}>
          {index > 0 ? ' · ' : ''}
          <Phrase field={first} candidate={candidate} />
        </span>
      ))}
      {' Alege valoarea înainte de exportul final.'}
    </EmaWidget>
  )
}

/** The annual cross-check (M4) for months that no longer add up to the filed annual reading. */
function MonthsBanner({ fields, year }: { fields: Field[]; year: number | null }) {
  const ctx = useJob()
  const [editing, setEditing] = useState(false)
  const issue = blockingIssues(ctx.checks.data).find(
    (item) => item.code === 'months_annual_mismatch',
  )
  const annual = fields.find((field) => field.id === issue?.field_id)
  if (!issue || !annual) return null
  const label = fieldLabel(annual.key, annual.label, year)
  const value = `${formatNumber(String(annual.value), annual.unit)} ${annual.unit ?? ''}`.trim()
  return (
    <div data-testid="months-annual-banner">
      <EmaWidget
        title="Suma lunilor nu se potriveşte cu totalul anual"
        actions={
          editing ? undefined : (
            <Button
              height={32}
              onClick={() => {
                setEditing(true)
              }}
            >
              Corectează totalul anual
            </Button>
          )
        }
      >
        {`${label}: totalul anual este ${value}. Corectează totalul sau lunile înainte de exportul final.`}
      </EmaWidget>
      {editing && (
        <ValueEditor
          field={annual}
          label={label}
          autoFocus
          onDone={() => {
            setEditing(false)
          }}
        />
      )}
    </div>
  )
}

/** S3 (M4 + 3c + M5): the data Ema read, what differs, what is missing, where each came from. */
export function DataTab({ camp }: { camp: string | null }) {
  const ctx = useJob()
  const reader = useReadDocuments()
  const missing = useMissing(ctx.jobId)
  const fields = ctx.fields.data
  if (!fields) return <p className="app-loading">Se încarcă…</p>
  const running = ctx.run?.state === 'running'
  const readButton = (
    <Button
      height={32}
      loading={reader.pending || running}
      disabled={reader.pending || running}
      onClick={() => {
        void reader.start()
      }}
    >
      Citeşte documentele
    </Button>
  )
  if (fields.length === 0) {
    return (
      <div className="data-empty">
        <EmptyState mark="brand" title="Datele nu au fost citite încă" actions={readButton}>
          Ema citeşte Anexa 2–3, Necesar info şi Prelucrare date; apoi verifici datele şi generezi
          programul.
        </EmptyState>
        <ProblemNotice problem={reader.problem} />
      </div>
    )
  }
  const year = ctx.job.data?.year ?? null
  const conflicts = fields.filter((field) => field.confidence === 'conflict')
  const blockingIds = new Set(blockingIssues(ctx.checks.data).map((issue) => issue.field_id))
  const missingRows = (missing.data ?? []).filter(
    (field) => field.required || blockingIds.has(field.id) || field.key.startsWith('identity.'),
  )
  return (
    <div className="data">
      {hasIssue(ctx.checks.data, 'import_required') && (
        <EmaWidget title="Documentele s-au schimbat" actions={readButton}>
          Citeşte-le din nou ca datele de aici să fie la zi.
        </EmaWidget>
      )}
      <ProblemNotice problem={reader.problem} />
      <Banner conflicts={conflicts} year={year} />
      <MonthsBanner fields={fields} year={year} />
      {(conflicts.length > 0 || missingRows.length > 0) && (
        <>
          <SectionKey>De decis</SectionKey>
          <div className="data__review">
            {conflicts.map((field) => (
              <ConflictRow
                key={`${field.id}${camp === field.id ? ':focus' : ''}`}
                field={field}
                focus={camp === field.id}
              />
            ))}
            {missingRows.map((field) => (
              <MissingRow key={field.id} field={field} />
            ))}
          </div>
        </>
      )}
      {carrierTables(fields).map((table) => (
        <CarrierTable key={table.carrier} table={table} />
      ))}
    </div>
  )
}
