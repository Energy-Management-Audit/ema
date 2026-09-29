import { useState } from 'react'
import type { ClientOverview } from '../../api/clients-types.ts'
import type { AnnexImport } from '../../api/clients-types.ts'
import type { ReportException, ReportingPreview } from '../../api/reporting-types.ts'
import { plural as roCount } from '../../lib/plural.ts'
import { formatReportFigure, previewRows, severityLabel, yearChip } from '../../reporting/view.ts'
import { Button } from '../../ui/Button.tsx'
import { SourceChip } from '../../ui/Chip.tsx'
import { CheckRow, Dialog } from '../../ui/Dialog.tsx'
import { MissingField } from '../../ui/Field.tsx'
import { GroupBox, SectionKey } from '../../ui/Surface.tsx'

/** M3: design handoff screen component. */
export function YearChips({
  years,
  selected,
  counts,
  onToggle,
}: {
  years: number[]
  selected: number[]
  counts?: Record<string, number>
  onToggle: (year: number) => void
}) {
  return (
    <div className="report-year-chips">
      {years.map((year, index) => (
        <button
          type="button"
          key={year}
          aria-pressed={selected.includes(year)}
          onClick={() => {
            onToggle(year)
          }}
        >
          {yearChip(year, counts?.[String(year)], index === 0)}
        </button>
      ))}
    </div>
  )
}

/** M3: design handoff screen component. */
export function ClientPickerDialog({
  clients,
  selected,
  onDone,
  onClose,
}: {
  clients: ClientOverview[]
  selected: string[]
  onDone: (ids: string[]) => void
  onClose: () => void
}) {
  const [chosen, setChosen] = useState(selected)
  return (
    <Dialog
      title="Alege clienţii"
      onClose={onClose}
      actions={
        <>
          <Button variant="secondary" height={36} onClick={onClose}>
            Renunţă
          </Button>
          <Button
            height={36}
            onClick={() => {
              onDone(chosen)
            }}
          >
            Gata
          </Button>
        </>
      }
      content={
        <div className="report-client-picker">
          <div>
            <Button
              variant="quiet"
              height={28}
              onClick={() => {
                setChosen(clients.map((item) => item.id))
              }}
            >
              Toţi
            </Button>
            <Button
              variant="quiet"
              height={28}
              onClick={() => {
                setChosen([])
              }}
            >
              Niciunul
            </Button>
          </div>
          {clients.map((client) => (
            <CheckRow
              key={client.id}
              checked={chosen.includes(client.id)}
              onChange={(checked) => {
                setChosen(
                  checked ? [...chosen, client.id] : chosen.filter((id) => id !== client.id),
                )
              }}
            >
              {client.name ?? client.cui ?? '—'}
            </CheckRow>
          ))}
        </div>
      }
    >
      Selectează clienţii pentru registru.
    </Dialog>
  )
}

/** M3: design handoff screen component. */
export function AnnexImportDialog({
  result,
  error,
  onClose,
}: {
  result: AnnexImport | null
  error: string | null
  onClose: () => void
}) {
  return (
    <Dialog
      title="Anexe adăugate"
      onClose={onClose}
      actions={
        <Button height={36} onClick={onClose}>
          Gata
        </Button>
      }
      content={
        <div className="report-import-dialog">
          {error && <p role="alert">{error}</p>}
          {result && (
            <>
              <SectionKey>ADĂUGATE {result.imported.length}</SectionKey>
              {result.imported.map((item) => (
                <div key={`${item.file_name}-${item.sha}`}>
                  {item.file_name} → {item.client_name ?? '—'} · {item.year}
                  {item.created && <span className="report-created">client nou</span>}
                </div>
              ))}
              <SectionKey>IGNORATE {result.ignored.length}</SectionKey>
              {result.ignored.map((item, index) => (
                <div key={`${item.file_name}-${String(index)}`}>
                  {item.file_name} · <span>{item.reason}</span>
                </div>
              ))}
            </>
          )}
        </div>
      }
    >
      Fiecare anexă a fost verificată după CUI.
    </Dialog>
  )
}

/** M3: design handoff screen component. */
export function PreviewTable({
  preview,
  year,
  years,
  onYearChange,
}: {
  preview: ReportingPreview
  year: number
  years: number[]
  onYearChange: (year: number) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const rows = preview.rows[String(year)] ?? []
  return (
    <section className="report-preview">
      <SectionKey>
        <button
          className="report-preview__year"
          type="button"
          onClick={() => {
            const current = years.indexOf(year)
            onYearChange(years[(current + 1) % years.length] ?? year)
          }}
        >
          {year} · PRIMELE RÂNDURI
        </button>
      </SectionKey>
      <div className="report-preview__table" role="table">
        <div className="report-preview__head" role="row">
          <span>NR.</span>
          <span>BENEFICIAR</span>
          <span>MĂSURI DE EFICIENŢĂ ENERGETICĂ</span>
          <span>ECONOMII (TEP)</span>
          <span>COST (MII LEI)</span>
        </div>
        {previewRows(preview, year, expanded).flatMap((company) =>
          company.measures.map((measure, index) => (
            <div
              className="report-preview__row"
              role="row"
              key={`${String(company.nr)}-${String(index)}`}
            >
              <span>{index === 0 ? company.nr : ''}</span>
              <span>{index === 0 ? company.beneficiary : ''}</span>
              <span>{measure.description}</span>
              <span className="ema-figures">
                {measure.saving_tep == null ? '—' : formatReportFigure(measure.saving_tep)}
              </span>
              <span className="ema-figures">
                {measure.cost_thousand_lei == null ? (
                  <MissingField width={70}>lipseşte</MissingField>
                ) : (
                  formatReportFigure(measure.cost_thousand_lei)
                )}
              </span>
            </div>
          )),
        )}
      </div>
      {rows.length > 5 && !expanded && (
        <button
          className="report-more"
          type="button"
          onClick={() => {
            setExpanded(true)
          }}
        >
          Toate cele {roCount(rows.length, 'societate', 'societăţi')}
        </button>
      )}
    </section>
  )
}

/** M3: design handoff screen component. */
export function ExceptionsBox({
  exceptions,
  clients,
}: {
  exceptions: ReportException[]
  clients: ClientOverview[]
}) {
  return (
    <section className="report-exceptions">
      <SectionKey>EXCEPŢII</SectionKey>
      <GroupBox>
        {exceptions.length === 0 ? (
          <p>Nicio excepţie.</p>
        ) : (
          exceptions.map((item, index) => {
            const label = severityLabel(item.code)
            const client = clients.find((one) => one.id === item.client_id)
            return (
              <div className="report-exceptions__row" key={`${item.client_id}-${String(index)}`}>
                <span
                  className={`report-exceptions__severity report-exceptions__severity--${label}`}
                >
                  {label}
                </span>
                <span>
                  {item.beneficiary ?? client?.name ?? item.source_name ?? '—'} · {item.detail}
                  {item.decision && <small> {item.decision}</small>}
                </span>
                {item.ref ? (
                  <SourceChip kind="document">{item.ref}</SourceChip>
                ) : (
                  <span className="ema-figures">{item.source_name ?? ''}</span>
                )}
              </div>
            )
          })
        )}
      </GroupBox>
    </section>
  )
}
