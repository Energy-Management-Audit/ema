import { useState } from 'react'
import type { SummaryFigure } from '../api/types.ts'
import { jobHref } from '../app/route.ts'
import { plural } from '../lib/plural.ts'
import { formatNumber } from '../lib/format.ts'
import { firstWithoutTerm, measureGroups } from '../piee/measures.ts'
import { useJob } from '../state/job.tsx'
import { Button } from '../ui/Button'
import { EmaWidget } from '../ui/Feedback'
import { AnnualCheckLine, CountBar, KpiTile } from '../ui/Figures'
import { EvidenceChip } from './EvidenceDetail.tsx'
import { MeasureRow } from './MeasureRow.tsx'
import './measures.css'

function figure(value: SummaryFigure | undefined): string {
  return value?.value ? formatNumber(value.value, value.unit, true) : '—'
}

function partial(value: SummaryFigure | undefined): string | undefined {
  return value?.value && value.missing.length > 0
    ? `fără ${plural(value.missing.length, 'măsură', 'măsuri')}`
    : undefined
}

const ANNUAL = {
  match: 'Totalul anual se potriveşte cu Anexa 2–3 · „Date anuale”',
  decided: 'Totalul anual a fost ales de tine; decizia e în Jurnal.',
  mismatch: 'Totalul anual nu se potriveşte cu Anexa 2–3',
  missing: 'Totalul din „Date anuale” lipseşte din Anexa 2–3.',
} as const

/** S4 (3g / 6c): the measures of the Anexa 2–3 with their sources and what they still lack. */
export function MeasuresTab() {
  const ctx = useJob()
  const [open, setOpen] = useState<{ id: string; focus: string | null } | null>(null)
  const summary = ctx.summary.data
  const fields = ctx.fields.data ?? []
  if (!summary || !ctx.fields.data) return <p className="app-loading">Se încarcă…</p>
  const totalField = fields.find((field) => field.id === summary.total_tep.field_ids[0])
  const conflict = fields.find(
    (field) => field.key === 'annual.total_tep' && field.confidence === 'conflict',
  )
  const next = firstWithoutTerm(fields)
  return (
    <div className="measures">
      <div className="measures__progress">
        <CountBar
          label="Măsuri gata de export"
          done={summary.measures_complete}
          total={summary.measures_total}
        />
      </div>
      <div className="measures__kpis">
        <div data-testid="kpi-savings">
          <KpiTile
            label="ECONOMIE ANGAJATĂ"
            value={figure(summary.savings_mwh)}
            unit="MWh/an"
            note={partial(summary.savings_mwh)}
          />
        </div>
        <div data-testid="kpi-investment">
          <KpiTile
            label="INVESTIŢIE"
            value={figure(summary.investment_thousand_lei)}
            unit="mii lei"
            note={partial(summary.investment_thousand_lei)}
          />
        </div>
        <div data-testid="kpi-total">
          <KpiTile
            label="TOTAL ENERGIE"
            value={figure(summary.total_tep)}
            unit="tep"
            source={
              totalField?.evidence?.[0] ? <EvidenceChip id={totalField.evidence[0]} /> : undefined
            }
          />
        </div>
        <AnnualCheckLine
          state={summary.annual_check}
          action={
            summary.annual_check === 'mismatch' && conflict ? (
              <a
                className="ema-btn ema-btn--primary ema-btn--h28"
                href={jobHref(ctx.jobId, 'date', conflict.id)}
              >
                Du-mă la conflict
              </a>
            ) : undefined
          }
        >
          {ANNUAL[summary.annual_check]}
        </AnnualCheckLine>
      </div>
      <EmaWidget
        title={`${String(summary.measures_total)} măsuri preluate din Anexa 2–3`}
        actions={
          summary.measures_without_term > 0 && next ? (
            <Button
              height={32}
              onClick={() => {
                setOpen({ id: next.id, focus: 'commissioning_year' })
              }}
            >
              Completează termenele
            </Button>
          ) : undefined
        }
      >
        {'Economiile şi investiţiile vin din Anexa 2–3.'}
        {summary.measures_without_term > 0
          ? ` Mai lipsesc termenele — ${String(summary.measures_without_term)} măsuri.`
          : ''}
      </EmaWidget>
      <div className="measures__table">
        <div className="measure-grid measure-grid--head">
          <span>MĂSURA</span>
          <span className="measure-grid__right">INVESTIŢIE mii lei</span>
          <span className="measure-grid__right">ECONOMIE MWh</span>
          <span className="measure-grid__right">RECUPERARE</span>
          <span>TERMEN</span>
          <span>SURSA</span>
        </div>
        {measureGroups(fields).map((group) => (
          <div key={group.group} className="measure-group">
            <span className="measure-group__title">{group.title}</span>
            {group.measures.map((measure) => (
              <MeasureRow
                key={measure.id}
                measure={measure}
                open={open?.id === measure.id}
                focus={open?.id === measure.id ? open.focus : null}
                onOpen={(column) => {
                  setOpen(column === null ? null : { id: measure.id, focus: column || null })
                }}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
