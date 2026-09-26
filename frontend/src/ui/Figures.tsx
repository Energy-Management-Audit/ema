import type { ReactNode } from 'react'
import './figures.css'

/** KPI tile "3g": the section key, the figure in 19px and its unit; an optional source below. */
export function KpiTile({
  label,
  value,
  unit,
  source,
  note,
}: {
  label: string
  value: ReactNode
  unit: string
  source?: ReactNode
  note?: ReactNode
}) {
  return (
    <div className="ema-kpi">
      <span className="ema-kpi__label">{label}</span>
      <strong className="ema-kpi__value">
        <span className="ema-figures">{value}</span> <span className="ema-kpi__unit">{unit}</span>
      </strong>
      {note && <span className="ema-kpi__note">{note}</span>}
      {source}
    </div>
  )
}

/** Count bar "3g": how many are ready, as a mono count and a 3px bar; amber until complete. */
export function CountBar({ label, done, total }: { label: string; done: number; total: number }) {
  const complete = total > 0 && done >= total
  const width = total > 0 ? Math.round((done / total) * 100) : 0
  return (
    <div className={`ema-count-bar ${complete ? 'ema-count-bar--complete' : ''}`}>
      <div className="ema-count-bar__line">
        <span className="ema-count-bar__label">{label}</span>
        <span className="ema-count-bar__count">
          {done} / {total}
        </span>
      </div>
      <span className="ema-count-bar__track">
        <span className="ema-count-bar__fill" style={{ width: `${String(width)}%` }} />
      </span>
    </div>
  )
}

/** The „Date anuale” cross-check line (OVERRIDES §1) in place of 3g's „Acoperire ţintă”. */
export function AnnualCheckLine({
  state,
  children,
  action,
}: {
  state: 'match' | 'decided' | 'mismatch' | 'missing'
  children: ReactNode
  action?: ReactNode
}) {
  const tone = state === 'match' || state === 'decided' ? 'ok' : 'warn'
  return (
    <div
      className={`ema-annual-check ema-annual-check--${tone}`}
      data-testid="annual-check"
      data-state={state}
    >
      <span className={`ema-dot ema-dot--${tone}`} aria-hidden />
      <span className="ema-annual-check__text">{children}</span>
      {action}
    </div>
  )
}
