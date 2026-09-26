import { Fragment, useState } from 'react'
import type { Field } from '../api/types.ts'
import { formatNumber } from '../lib/format.ts'
import type { CarrierRow, CarrierTable as Table } from '../piee/dataset.ts'
import { carrierLabel, fieldLabel, MONTHS } from '../piee/labels.ts'
import { useJob } from '../state/job.tsx'
import { MissingField } from '../ui/Field'
import { Card } from '../ui/Surface'
import { EvidenceChip, EvidenceDetail } from './EvidenceDetail.tsx'
import { ValueEditor } from './ValueEditor.tsx'

const SHORT = [0, 1, 2, 3]

function Figure({ field, unit }: { field: Field; unit: string }) {
  const text =
    typeof field.value === 'string' || typeof field.value === 'number' ? String(field.value) : ''
  const own = field.unit && field.unit !== unit ? ` ${field.unit}` : ''
  return <>{`${formatNumber(text, field.unit)}${own}`}</>
}

/** A found figure is click-to-correct: a `correct` decision on the field's revision (3c). */
function Editable({
  field,
  unit,
  onEdit,
}: {
  field: Field
  unit: string
  onEdit: (field: Field) => void
}) {
  const { job } = useJob()
  return (
    <button
      type="button"
      className="carrier-table__figure"
      aria-label={`Corectează ${fieldLabel(field.key, field.label, job.data?.year ?? null)}`}
      onClick={() => {
        onEdit(field)
      }}
    >
      <Figure field={field} unit={unit} />
    </button>
  )
}

type Cells = { row: CarrierRow; months: number[]; unit: string; onEdit: (field: Field) => void }

function MonthCells({ row, months, unit, onEdit }: Cells) {
  return (
    <>
      {months.map((index) => {
        const cell = row.months?.[index]
        return (
          <td key={index} className="carrier-table__n">
            {cell?.kind === 'value' ? (
              <Editable field={cell.field} unit={unit} onEdit={onEdit} />
            ) : (
              <MissingField width={70}>lipseşte</MissingField>
            )}
          </td>
        )
      })}
    </>
  )
}

/** One carrier's three years (M4): mono figures, the missing months dashed, the source chip. */
export function CarrierTable({ table }: { table: Table }) {
  const [expanded, setExpanded] = useState(false)
  const [openYear, setOpenYear] = useState<number | null>(null)
  const [editing, setEditing] = useState<Field | null>(null)
  const { job } = useJob()
  const edit = (field: Field) => {
    setEditing(editing?.id === field.id ? null : field)
  }
  const head = expanded ? MONTHS.map((_, index) => index) : SHORT
  const toggle = (
    <th className="carrier-table__n">
      <button
        type="button"
        className="carrier-table__more"
        aria-label="Arată toate lunile"
        aria-expanded={expanded}
        onClick={() => {
          setExpanded(!expanded)
        }}
      >
        …
      </button>
    </th>
  )
  const columns = 1 + head.length + (expanded ? 1 : 2) + 2
  return (
    <div data-testid={`carrier-table-${table.carrier}`}>
      <Card>
        <div className="carrier-table__heading">
          {`${carrierLabel(table.carrier)} · ${table.unit}`}
        </div>
        <div className={`carrier-table__scroll ${expanded ? 'carrier-table__scroll--wide' : ''}`}>
          <table className="carrier-table">
            <thead>
              <tr>
                <th>An</th>
                {head.map((index) => (
                  <th key={index} className="carrier-table__n">
                    {MONTHS[index]}
                  </th>
                ))}
                {toggle}
                {!expanded && <th className="carrier-table__n">Dec</th>}
                <th className="carrier-table__n">Total</th>
                <th>Sursă</th>
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row) => {
                const evidence = row.annual?.evidence?.[0]
                return (
                  <Fragment key={row.year}>
                    <tr>
                      <td className="carrier-table__year">{row.year}</td>
                      {row.months === null ? (
                        <td colSpan={head.length + (expanded ? 2 : 3)}>
                          <span className="carrier-table__annual-only">
                            <span className="carrier-table__missing">
                              date lunare indisponibile
                            </span>
                            {row.annual
                              ? ` · doar totalul anual, ${formatNumber(String(row.annual.value), row.annual.unit)} ${row.annual.unit ?? table.unit}`
                              : ''}
                          </span>
                        </td>
                      ) : (
                        <>
                          <MonthCells row={row} months={head} unit={table.unit} onEdit={edit} />
                          <td className="carrier-table__n">…</td>
                          {!expanded && (
                            <MonthCells row={row} months={[11]} unit={table.unit} onEdit={edit} />
                          )}
                          <td className="carrier-table__n carrier-table__total">
                            {row.annual?.value !== undefined && row.annual.value !== null ? (
                              <Editable field={row.annual} unit={table.unit} onEdit={edit} />
                            ) : (
                              '—'
                            )}
                          </td>
                        </>
                      )}
                      <td>
                        {evidence && (
                          <EvidenceChip
                            id={evidence}
                            onClick={() => {
                              setOpenYear(openYear === row.year ? null : row.year)
                            }}
                          />
                        )}
                      </td>
                    </tr>
                    {editing?.key.split('.')[2] === String(row.year) && (
                      <tr className="carrier-table__detail">
                        <td colSpan={columns}>
                          <ValueEditor
                            key={editing.id}
                            field={editing}
                            label={fieldLabel(editing.key, editing.label, job.data?.year ?? null)}
                            autoFocus
                            onDone={() => {
                              setEditing(null)
                            }}
                          />
                        </td>
                      </tr>
                    )}
                    {openYear === row.year && evidence && (
                      <tr className="carrier-table__detail">
                        <td colSpan={columns}>
                          <EvidenceDetail id={evidence} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
