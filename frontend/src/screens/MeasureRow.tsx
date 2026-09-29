import type { ReactNode } from 'react'
import { ChevronRight, Sheet } from 'lucide-react'
import type { Field } from '../api/types.ts'
import { formatNumber } from '../lib/format.ts'
import { hasValue } from '../piee/dataset.ts'
import { cellReference, fieldLabel } from '../piee/labels.ts'
import { missingColumns, type MeasureView } from '../piee/measures.ts'
import { useJob } from '../state/job.tsx'
import { MissingField } from '../ui/Field'
import { Icon } from '../ui/Icon'
import { SectionKey } from '../ui/Surface'
import { fieldValue, useEvidence } from './EvidenceDetail.tsx'
import { ValueEditor } from './ValueEditor.tsx'

function text(field: Field | undefined): string {
  if (!hasValue(field)) return ''
  return typeof field.value === 'string' || typeof field.value === 'number'
    ? String(field.value)
    : ''
}

function SourceLabel({ field }: { field: Field | undefined }) {
  const evidence = useEvidence(field?.evidence?.[0])
  const sheet = evidence.data?.locator?.sheet
  return <>{sheet ? `Anexa 2–3 · ${sheet}` : 'Anexa 2–3'}</>
}

function CellRef({ field }: { field: Field }) {
  const evidence = useEvidence(field.evidence?.[0])
  return (
    <span className="measure-open__ref">{evidence.data ? cellReference(evidence.data) : ''}</span>
  )
}

/** One measure of 3g: figures, term, source; a gap is a dashed „lipseşte” that opens its editor. */
export function MeasureRow({
  measure,
  open,
  focus,
  onOpen,
}: {
  measure: MeasureView
  open: boolean
  focus: string | null
  onOpen: (column: string | null) => void
}) {
  const { job } = useJob()
  const year = job.data?.year ?? null
  const columns = measure.columns
  const cell = (column: string, render: (field: Field) => ReactNode) => {
    const field = columns[column]
    if (!field) return <span className="measure-row__n measure-row__muted">—</span>
    if (!hasValue(field)) {
      return (
        <span className="measure-row__n">
          <MissingField
            width={96}
            onClick={() => {
              onOpen(column)
            }}
          >
            lipseşte
          </MissingField>
        </span>
      )
    }
    return <span className="measure-row__n">{render(field)}</span>
  }
  const gaps = missingColumns(measure)
  return (
    <div
      className={`measure-row ${open ? 'measure-row--open' : ''}`}
      data-testid={`measure-row-${measure.id}`}
    >
      <div className="measure-grid measure-row__main">
        <span className="measure-row__name">
          <span className="measure-row__title">{text(columns.description) || '—'}</span>
          {text(columns.location) && (
            <span className="measure-row__detail">{text(columns.location)}</span>
          )}
        </span>
        {cell('investment_thousand_lei', (field) => formatNumber(text(field), field.unit))}
        {cell('saving_mwh', (field) => formatNumber(text(field), field.unit))}
        {cell('payback_years', (field) => (
          <>
            {`${formatNumber(text(field), 'ani', true)} ani`}
            {field.state === 'calculated' && <span className="measure-row__muted"> calculat</span>}
          </>
        ))}
        {cell('commissioning_year', (field) => text(field))}
        <button
          type="button"
          className="measure-row__source"
          aria-expanded={open}
          onClick={() => {
            onOpen(open ? null : '')
          }}
        >
          <Icon icon={Sheet} size={13} stroke={1.6} />
          <span className="measure-row__source-text">
            <SourceLabel field={columns.description} />
          </span>
          <Icon icon={ChevronRight} size={12} stroke={1.8} />
        </button>
      </div>
      {open && (
        <div className="measure-open">
          <div className="measure-open__block">
            <SectionKey>Din Anexa 2–3</SectionKey>
            {Object.values(columns)
              .filter((field) => hasValue(field))
              .map((field) => (
                <div className="measure-open__line" key={field.id}>
                  <span>{fieldLabel(field.key, field.label, year)}</span>
                  <span className={field.value_type === 'text' ? undefined : 'ema-figures'}>
                    {fieldValue(field)}
                  </span>
                  <CellRef field={field} />
                </div>
              ))}
          </div>
          {gaps.length > 0 && (
            <div className="measure-open__block">
              <SectionKey>Ce mai trebuie pentru PIEE</SectionKey>
              {gaps.map((column) => {
                const field = columns[column]
                if (!field) return null
                const label = fieldLabel(field.key, field.label, year)
                return (
                  <div className="measure-open__editor" key={column}>
                    <span>{label}</span>
                    <ValueEditor
                      field={field}
                      label={label}
                      autoFocus={focus === column}
                      onDone={() => {
                        onOpen(null)
                      }}
                    />
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
