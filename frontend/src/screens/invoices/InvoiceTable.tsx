import { useMemo } from 'react'
import type { InvoiceBatchView, InvoiceRow as InvoiceDataRow } from '../../api/invoices-types.ts'
import { useBlobUrl } from '../../api/blobUrl.ts'
import { invoicesApi } from '../../api/invoices.ts'
import { monthBars } from '../../invoices/bars.ts'
import {
  formatInvoiceNumber,
  monthName,
  outlierPercent,
  romanianCount,
} from '../../invoices/labels.ts'
import { Button } from '../../ui/Button.tsx'
import { EmaWidget, FailureNotice } from '../../ui/Feedback.tsx'
import { CountBar, KpiTile } from '../../ui/Figures.tsx'
import { Highlight, SourceButton } from '../../ui/Review.tsx'
import { Paper, Card, CardHeader, SectionKey } from '../../ui/Surface.tsx'

const FILE_STATUS: Record<string, string> = {
  exportable: 'extras',
  failed: 'eşuat',
  requires_review: 'de revizuit',
  unsupported: 'nesuportat',
  incompatible: 'incompatibil',
  duplicate: 'duplicat',
}

function snippetWithValue(snippet: string, value: string | null) {
  if (!value) return snippet
  const digits = value.replace(/\D/g, '')
  const candidate = [...snippet.matchAll(/\d[\d.,\s]*\d|\d/g)].find(
    (match) => match[0].replace(/\D/g, '') === digits,
  )
  if (!candidate) return snippet
  const at = candidate.index
  return (
    <>
      {snippet.slice(0, at)}
      <Highlight>{candidate[0]}</Highlight>
      {snippet.slice(at + candidate[0].length)}
    </>
  )
}

export function MonthBars({ year, rows }: { year: number; rows: InvoiceDataRow[] }) {
  return (
    <div className="invoice-bars" aria-label={`Consum lunar ${String(year)}`}>
      {monthBars(year, rows).map((bar) => (
        <span
          key={bar.month}
          className={`invoice-bars__bar ${bar.missing ? 'invoice-bars__bar--missing' : ''} ${bar.outlier ? 'invoice-bars__bar--outlier' : ''}`}
          style={{ height: `${String(bar.height)}%` }}
          title={`${monthName(bar.month)} ${String(year)}`}
        />
      ))}
    </div>
  )
}

export function KpiStrip({ batch }: { batch: InvoiceBatchView }) {
  const year = batch.year ?? new Date().getFullYear()
  return (
    <>
      <div className="invoice-count">
        <CountBar label="Luni încărcate" done={batch.totals.months} total={12} />
      </div>
      <div className="invoice-kpis">
        <KpiTile
          label="CONSUM TOTAL"
          value={formatInvoiceNumber(String(Number(batch.totals.consumption_kwh) / 1000), 2)}
          unit="MWh"
        />
        <KpiTile
          label="VALOARE ENERGIE ACTIVĂ"
          value={formatInvoiceNumber(batch.totals.value_lei, 2)}
          unit="lei"
        />
        <KpiTile
          label="PREŢ MEDIU"
          value={formatInvoiceNumber(batch.totals.price_avg_lei_kwh, 4)}
          unit="lei/kWh"
        />
        <MonthBars year={year} rows={batch.rows} />
      </div>
    </>
  )
}

export function FailedFiles({
  batch,
  onReplace,
  onRemove,
}: {
  batch: InvoiceBatchView
  onReplace: (slot: string) => void
  onRemove: (slot: string) => void
}) {
  const failed = batch.files.filter((file) => file.status === 'failed')
  if (!failed.length) return null
  const total = new Set([
    ...batch.rows.map((row) => row.slot),
    ...batch.files.map((file) => file.slot),
  ]).size
  const listed = new Map<string, { file_name: string; status: string }>()
  for (const file of [...batch.files, ...batch.rows]) {
    if (file.slot && !listed.has(file.slot))
      listed.set(file.slot, { file_name: file.file_name, status: file.status })
  }
  return (
    <Card>
      <CardHeader
        title="Documente"
        count={`${String(total - failed.length)} din ${String(total)}`}
      />
      <div className="invoice-failed">
        {failed.map((file) => (
          <FailureNotice
            key={file.slot}
            title={`${file.file_name} nu a putut fi citită`}
            actions={
              <div className="invoice-failed__actions">
                <Button
                  height={30}
                  onClick={() => {
                    onReplace(file.slot)
                  }}
                >
                  Reîncarcă
                </Button>
                <Button
                  variant="secondary"
                  height={30}
                  onClick={() => {
                    onRemove(file.slot)
                  }}
                >
                  Scoate
                </Button>
              </div>
            }
          >
            {file.reason}
          </FailureNotice>
        ))}
        <p>
          {total - failed.length === 1 ? 'Cealaltă' : 'Celelalte'}{' '}
          {romanianCount(total - failed.length, 'factură', 'facturi')}{' '}
          {total - failed.length === 1 ? 'a fost procesată' : 'au fost procesate'}. Eroarea nu
          opreşte lucrarea.
        </p>
        <ul className="invoice-failed__list" aria-label="Starea fişierelor">
          {[...listed].map(([slot, file]) => (
            <li key={slot}>
              <span>{file.file_name}</span>
              <small>{FILE_STATUS[file.status] ?? file.status}</small>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  )
}

export function InvoiceOpen({ jobId, row }: { jobId: string; row: InvoiceDataRow }) {
  const page = row.sources.active_energy?.page ?? 1
  const pageLoader = useMemo(
    () => () => invoicesApi.pagePng(jobId, row.slot, page, true),
    [jobId, row.slot, page],
  )
  const pdfLoader = useMemo(() => () => invoicesApi.invoicePdf(jobId, row.slot), [jobId, row.slot])
  const pageUrl = useBlobUrl(pageLoader)
  const pdfUrl = useBlobUrl(pdfLoader)
  const snippet = row.sources.active_energy?.snippet ?? ''
  return (
    <div className="invoice-open">
      <div className="invoice-open__left">
        <Paper className="invoice-open__paper">
          {pageUrl ? (
            <img src={pageUrl} alt={`${row.file_name}, pagina ${String(page)}`} />
          ) : (
            <span>Se încarcă…</span>
          )}
        </Paper>
        <Button
          variant="secondary"
          height={28}
          disabled={!pdfUrl}
          onClick={() => {
            if (pdfUrl) window.open(pdfUrl, '_blank', 'noopener')
          }}
        >
          Deschide factura
        </Button>
      </div>
      <div className="invoice-open__right">
        <SectionKey>CE SCRIE PE FACTURĂ</SectionKey>
        <p>„{snippetWithValue(snippet, row.consumption_kwh)}”</p>
        {row.outlier && (
          <>
            <SectionKey>DE CE E MARCATĂ</SectionKey>
            <p>
              Consumul lunii e cu {outlierPercent(row.outlier.ratio)} % peste media lunilor vecine (
              {formatInvoiceNumber(row.outlier.neighbours_mean_kwh)} kWh).
            </p>
          </>
        )}
      </div>
    </div>
  )
}

export function InvoiceRow({
  jobId,
  row,
  open,
  onToggle,
}: {
  jobId: string
  row: InvoiceDataRow
  open: boolean
  onToggle: () => void
}) {
  const page = row.sources.active_energy?.page
  const date = row.invoice_date
    ? `${row.invoice_date.slice(8, 10)}.${row.invoice_date.slice(5, 7)}`
    : ''
  return (
    <div className={`invoice-row ${open ? 'invoice-row--open' : ''}`} role="row">
      <div className="invoice-row__cells">
        <span role="cell">{monthName(row.month)}</span>
        <span role="cell" className="invoice-row__invoice">
          <span>
            {row.supplier} {row.invoice_number} {date && `· ${date}`}
          </span>
          {row.outlier && <small className="invoice-row__outlier">peste tipar</small>}
          {row.status === 'requires_review' && (
            <small className="invoice-row__review">nu intră în export · {row.issues[0]}</small>
          )}
        </span>
        <span role="cell" className="invoice-row__number">
          {formatInvoiceNumber(row.consumption_kwh)}
        </span>
        <span role="cell" className="invoice-row__number">
          {formatInvoiceNumber(row.value_lei)}
        </span>
        <span role="cell" className="invoice-row__number">
          {row.price_lei_kwh === null
            ? '—'
            : formatInvoiceNumber(
                row.price_lei_kwh,
                Math.min(4, Math.max(3, row.price_lei_kwh.split('.')[1]?.length ?? 3)),
              )}
        </span>
        <span role="cell">
          {page && row.slot ? (
            <SourceButton open={open} onClick={onToggle}>
              PDF · pag. {page}
            </SourceButton>
          ) : (
            '—'
          )}
        </span>
      </div>
      {open && <InvoiceOpen jobId={jobId} row={row} />}
    </div>
  )
}

export function MissingMonthRow({ month, onAdd }: { month: string; onAdd: () => void }) {
  return (
    <div className="invoice-row invoice-row--missing" role="row">
      <div className="invoice-row__cells">
        <span role="cell">{monthName(month)}</span>
        <span role="cell">factura lipseşte</span>
        <span role="cell">—</span>
        <span role="cell">—</span>
        <span role="cell">—</span>
        <span role="cell">
          <Button variant="secondary" height={30} onClick={onAdd}>
            Adaug-o
          </Button>
        </span>
      </div>
    </div>
  )
}

export function InvoiceTable({
  jobId,
  batch,
  openId,
  onOpen,
  onAdd,
  onReplace,
  onRemove,
}: {
  jobId: string
  batch: InvoiceBatchView
  openId: string | null
  onOpen: (id: string) => void
  onAdd: () => void
  onReplace: (slot: string) => void
  onRemove: (slot: string) => void
}) {
  const outlier = batch.rows.find((row) => row.outlier)
  const items = [
    ...batch.rows.map((row) => ({ month: row.month, id: row.id, row })),
    ...batch.missing_months.map((month) => ({ month, id: `missing-${month}`, row: null })),
  ].sort((a, b) => (a.month ?? '9999').localeCompare(b.month ?? '9999'))
  return (
    <div className="invoice-table">
      <KpiStrip batch={batch} />
      {outlier?.outlier && (
        <EmaWidget
          title={`${monthName(outlier.month).replace(/^./, (char) => char.toUpperCase())} e cu ${String(outlierPercent(outlier.outlier.ratio))} % peste media lunilor vecine`}
          actions={
            <Button
              height={32}
              onClick={() => {
                onOpen(outlier.id)
              }}
            >
              Vezi {monthName(outlier.month)}
            </Button>
          }
        >
          Poate fi o citire de regularizare. Verifică factura înainte de export.
        </EmaWidget>
      )}
      <FailedFiles batch={batch} onReplace={onReplace} onRemove={onRemove} />
      <div className="invoice-table__head" role="row">
        <span>LUNA</span>
        <span>FACTURA</span>
        <span>CONSUM kWh</span>
        <span>VALOARE lei</span>
        <span>LEI/kWh</span>
        <span>SURSA</span>
      </div>
      <div className="invoice-table__rows" role="table" aria-label="Facturi">
        {items.map((item) =>
          item.row ? (
            <InvoiceRow
              key={item.id}
              jobId={jobId}
              row={item.row}
              open={openId === item.id}
              onToggle={() => {
                onOpen(item.id)
              }}
            />
          ) : (
            <MissingMonthRow key={item.id} month={item.month} onAdd={onAdd} />
          ),
        )}
      </div>
    </div>
  )
}
