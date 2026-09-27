import { Check } from 'lucide-react'
import { countRo, type TocItem } from '../../audit/report.ts'
import { Icon } from '../../ui/Icon'
import { SectionKey } from '../../ui/Surface'

/** 3d CUPRINS: each chapter done, being written or still to do; a click shows its page. */
export function ReportToc({
  items,
  markers,
  onJump,
  onMarkers,
}: {
  items: TocItem[]
  markers: number
  onJump?: (page: number | null) => void
  onMarkers?: () => void
}) {
  return (
    <nav className="report-toc" aria-label="Cuprins" data-testid="report-toc">
      <SectionKey>CUPRINS</SectionKey>
      {items.map((item) => (
        <button
          key={item.number}
          type="button"
          className={`report-toc__item report-toc__item--${item.state}`}
          data-state={item.state}
          disabled={!onJump || item.page === null}
          onClick={() => {
            onJump?.(item.page)
          }}
        >
          <span className="report-toc__mark" aria-hidden>
            {item.state === 'done' && (
              <Icon icon={Check} size={12} stroke={2.6} color="var(--olive-mark)" />
            )}
            {item.state === 'working' && <span className="ema-spinner ema-spinner--11" />}
            {item.state === 'todo' && '·'}
          </span>
          <span className="report-toc__title" title={item.title}>
            {`${String(item.number)} · ${item.title}`}
          </span>
          {item.page !== null && <span className="report-toc__page">{item.page}</span>}
        </button>
      ))}
      {markers > 0 && (
        <button
          type="button"
          className="report-toc__markers"
          onClick={() => {
            onMarkers?.()
          }}
        >
          <span className="report-toc__mark" aria-hidden>
            !
          </span>
          {countRo(markers, 'câmp gol', 'câmpuri goale')}
        </button>
      )}
    </nav>
  )
}
