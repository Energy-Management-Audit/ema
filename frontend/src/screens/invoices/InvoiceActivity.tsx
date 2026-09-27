import type { InvoiceBatchView, InvoiceIdentity } from '../../api/invoices-types.ts'
import type { Decision, Output } from '../../api/types.ts'
import { formatBytes, rel } from '../../lib/format.ts'
import {
  monthName,
  outlierPercent,
  romanianCount,
  statusSingular,
  statusWord,
} from '../../invoices/labels.ts'
import { ActivityEntry, ActivityPanel } from '../../ui/Activity.tsx'
import { RunPanel } from '../RunPanel.tsx'

export function InvoiceActivity({
  view,
  batch,
  identity,
  decisions,
  output,
  year,
  onUndo,
  clientFieldId,
}: {
  view: string
  batch: InvoiceBatchView | undefined
  identity: InvoiceIdentity | undefined
  decisions: Decision[]
  output: Output | undefined
  year: number | null
  onUndo: (id: string) => void
  clientFieldId: string | undefined
}) {
  const confirmed = decisions.findLast(
    (item) => item.action === 'accept' && !item.undone_by && item.field_id === clientFieldId,
  )
  const statusCounts = new Map<string, number>()
  for (const row of batch?.rows ?? [])
    statusCounts.set(row.status, (statusCounts.get(row.status) ?? 0) + 1)
  for (const file of batch?.files ?? [])
    statusCounts.set(file.status, (statusCounts.get(file.status) ?? 0) + 1)
  const statusText = [...statusCounts]
    .map(([status, count]) =>
      romanianCount(
        count,
        statusSingular(status),
        status === 'exportable' ? 'citite' : statusWord(status),
      ),
    )
    .join(' · ')
  const marked = [
    ...new Map(
      (batch?.rows ?? []).filter((row) => row.outlier).map((row) => [row.month, row]),
    ).values(),
  ]
  const months =
    batch?.missing_months.filter(
      (month) => year === null || month.startsWith(`${String(year)}-`),
    ) ?? []
  return (
    <ActivityPanel
      title="Ce s-a întâmplat"
      footer={
        view === 'identity' ? (
          'După confirmare, POD-ul şi CUI-ul se ţin minte pentru loturile următoare. Anularea confirmării le retrage.'
        ) : view === 'table' ? (
          <>
            <strong>
              ANUL {year ?? '—'} · {batch?.totals.months ?? 0} / 12
            </strong>
            <span
              className="invoice-activity__progress"
              role="progressbar"
              aria-label={`Luni încărcate în ${String(year ?? 'an')}`}
              aria-valuenow={batch?.totals.months ?? 0}
              aria-valuemin={0}
              aria-valuemax={12}
            >
              <span style={{ width: `${String(((batch?.totals.months ?? 0) / 12) * 100)}%` }} />
            </span>
            <p>
              {months.length
                ? `Fără ${months.map(monthName).join(', ')}, totalul anual rămâne incomplet.`
                : 'Toate lunile anului sunt încărcate.'}
            </p>
          </>
        ) : undefined
      }
    >
      {view === 'reading' && <RunPanel />}
      {view === 'identity' && (
        <>
          <ActivityEntry
            outcome="info"
            title={romanianCount(identity?.files_total ?? 0, 'PDF citit', 'PDF citite')}
            time=""
            detail={statusText}
          />
          <ActivityEntry
            outcome="info"
            title="Client propus din facturi"
            time=""
            detail={
              identity?.memory.length
                ? 'găsit în memoria CUI/POD'
                : 'nu există încă în memoria CUI/POD'
            }
          />
        </>
      )}
      {view === 'table' && (
        <>
          <ActivityEntry
            outcome="info"
            title={romanianCount(
              new Set(batch?.rows.map((row) => row.slot) ?? []).size,
              'factură citită',
              'facturi citite',
            )}
            time={batch?.read_ended_at ? rel(batch.read_ended_at) : ''}
            detail="consum, valoare şi preţ unitar din fiecare"
          />
          {marked.map(
            (row) =>
              row.outlier && (
                <ActivityEntry
                  key={row.month}
                  outcome="info"
                  title={`${monthName(row.month)} iese din tipar`}
                  time=""
                  detail={`${String(outlierPercent(row.outlier.ratio))} % peste lunile vecine`}
                />
              ),
          )}
          {confirmed && (
            <ActivityEntry
              outcome="accepted"
              title="Client confirmat"
              time={rel(confirmed.at)}
              undo="Anulează"
              onUndo={() => {
                onUndo(confirmed.id)
              }}
            />
          )}
          {output && (
            <ActivityEntry
              outcome="info"
              title="Excel generat"
              time={output.created_at ? rel(output.created_at) : ''}
              detail={`Facturi.xlsx · ${formatBytes(output.size_bytes)}`}
            />
          )}
        </>
      )}
    </ActivityPanel>
  )
}
