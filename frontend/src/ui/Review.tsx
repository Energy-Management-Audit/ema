import type { ReactNode } from 'react'
import { ChevronRight, ExternalLink, File, Sheet, type LucideIcon } from 'lucide-react'
import { Button } from './Button'
import { Icon } from './Icon'
import { Paper } from './Surface'
import './review.css'

/** Source button "3c": the document and page a value came from; opens the snippet in line.
 * `cell` for a spreadsheet reference (F2!C14). */
export function SourceButton({
  children,
  open = false,
  cell = false,
  onClick,
}: {
  children: ReactNode
  open?: boolean
  cell?: boolean
  onClick?: () => void
}) {
  const glyph: LucideIcon = cell ? Sheet : File
  return (
    <button type="button" className="ema-source-btn" aria-expanded={open} onClick={onClick}>
      <Icon icon={glyph} size={14} stroke={1.6} />
      {children}
      <Icon icon={ChevronRight} size={13} stroke={1.8} className="ema-source-btn__chevron" />
    </button>
  )
}

/** Field review row "3c": the label and its review state, the value (with what it is), its
 * source, and the actions. Open, it is the only row that gets a surface, with the snippet below. */
export function FieldReviewRow({
  label,
  status,
  value,
  note,
  source,
  actions,
  snippet,
}: {
  label: ReactNode
  status: ReactNode
  value: ReactNode
  note?: ReactNode
  source?: ReactNode
  actions?: ReactNode
  snippet?: ReactNode
}) {
  const open = snippet !== undefined
  return (
    <div className={`ema-review-row ${open ? 'ema-review-row--open' : ''}`}>
      <div className="ema-review-row__main">
        <div className="ema-review-row__label">
          <span>{label}</span>
          {status}
        </div>
        <div className="ema-review-row__value">
          {value}
          {note && <span className="ema-review-row__note">{note}</span>}
        </div>
        {source}
        {actions && <div className="ema-review-row__actions">{actions}</div>}
      </div>
      {open && <div className="ema-review-row__snippet">{snippet}</div>}
    </div>
  )
}

/** The value of a review row: the figure, or the rejected value struck through beside the new one. */
export function ReviewValue({ children, previous }: { children: ReactNode; previous?: ReactNode }) {
  return (
    <>
      {previous !== undefined && (
        <>
          <span className="ema-review-value__previous">{previous}</span>
          <span className="ema-review-value__arrow">→</span>
        </>
      )}
      <strong className="ema-review-value">{children}</strong>
    </>
  )
}

/** The page crop "3c": paper with the value's line highlighted, then „Deschide pagina” and the
 * mono reference. The page is drawn schematically until the API serves real crops (S17b). */
export function PageCrop({
  label,
  value,
  page,
  reference,
}: {
  label: string
  value: string
  page: number
  reference: string
}) {
  return (
    <div className="ema-page-crop">
      <Paper className="ema-page-crop__paper">
        <span
          className="ema-page-crop__line ema-page-crop__line--heading"
          style={{ width: '52%' }}
        />
        {[88, 80].map((width) => (
          <span
            key={width}
            className="ema-page-crop__line"
            style={{ width: `${String(width)}%` }}
          />
        ))}
        <span
          className="ema-page-crop__line ema-page-crop__line--before"
          style={{ width: '40%' }}
        />
        <div className="ema-page-crop__hit">
          <span className="ema-page-crop__hit-label">{label}</span>
          <span className="ema-page-crop__hit-rule" />
          <span className="ema-page-crop__hit-value">{value}</span>
        </div>
        <span className="ema-page-crop__line ema-page-crop__line--after" style={{ width: '76%' }} />
        {[84, 30].map((width) => (
          <span
            key={width}
            className="ema-page-crop__line"
            style={{ width: `${String(width)}%` }}
          />
        ))}
        <span className="ema-page-crop__number">{page}</span>
      </Paper>
      <div className="ema-page-crop__footer">
        <Button variant="secondary" height={28} iconAfter={ExternalLink}>
          Deschide pagina
        </Button>
        <span className="ema-page-crop__reference">{reference}</span>
      </div>
    </div>
  )
}

/** The snippet "3c": the page crop beside the whole sentence (value marked) and why Ema is unsure,
 * with its exits. */
export function Snippet({
  crop,
  quote,
  reasonTitle,
  reason,
  exits,
}: {
  crop: ReactNode
  quote: ReactNode
  reasonTitle: ReactNode
  reason: ReactNode
  exits: ReactNode
}) {
  return (
    <>
      {crop}
      <div className="ema-snippet__text">
        <div className="ema-snippet__block">
          <span className="ema-section-key">Textul din document</span>
          <p className="ema-snippet__quote">{quote}</p>
        </div>
        <div className="ema-snippet__block">
          <span className="ema-section-key">{reasonTitle}</span>
          <p className="ema-snippet__reason">{reason}</p>
          <div className="ema-snippet__exits">{exits}</div>
        </div>
      </div>
    </>
  )
}

/** The value highlighted inside a quote "3c". */
export function Highlight({ children }: { children: ReactNode }) {
  return <mark className="ema-highlight">{children}</mark>
}
