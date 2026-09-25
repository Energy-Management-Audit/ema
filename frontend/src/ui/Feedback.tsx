import type { ReactNode } from 'react'
import { Check } from 'lucide-react'
import { Exclamation, Icon } from './Icon'
import { BrandMark } from './Surface'
import './feedback.css'

/** Ema widget "7d": one prompt, never a list. The text says why, not only what; at most two
 * actions. */
export function EmaWidget({
  title,
  children,
  actions,
}: {
  title: ReactNode
  children: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="ema-widget">
      <BrandMark size={30} />
      <div className="ema-widget__text">
        <strong>{title}</strong>
        <span>{children}</span>
      </div>
      {actions}
    </div>
  )
}

/** Progress bar "3c/7b": thin (3px) in panels; the 5px bar of 7b sweeps while work runs. */
export function ProgressBar({ value, running = false }: { value: number; running?: boolean }) {
  return (
    <span
      className={`ema-progress ${running ? 'ema-progress--running' : ''}`}
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <span className="ema-progress__fill" style={{ width: `${String(value)}%` }}>
        {running && <span className="ema-progress__sweep" />}
      </span>
    </span>
  )
}

/** Empty state "7b": one thing to do, explained in two lines, the next step as the action. */
export function EmptyState({
  title,
  children,
  actions,
  footnote,
  mark,
}: {
  title: ReactNode
  children: ReactNode
  actions: ReactNode
  footnote?: ReactNode
  mark: 'brand' | 'done'
}) {
  return (
    <div className={`ema-empty ema-empty--${mark}`}>
      {mark === 'brand' ? (
        <BrandMark size={38} />
      ) : (
        <span className="ema-empty__done">
          <Icon icon={Check} size={17} stroke={2.4} color="var(--olive-ink)" />
        </span>
      )}
      <h2>{title}</h2>
      <p>{children}</p>
      <div className="ema-empty__actions">{actions}</div>
      {footnote && <span className="ema-empty__footnote">{footnote}</span>}
    </div>
  )
}

/** A per-item failure "7b": the concrete cause and threshold, and two exits. */
export function FailureNotice({
  title,
  children,
  actions,
}: {
  title: ReactNode
  children: ReactNode
  actions: ReactNode
}) {
  return (
    <div className="ema-failure" role="alert">
      <span className="ema-failure__icon">
        <Icon icon={Exclamation} size={15} stroke={1.9} />
      </span>
      <div className="ema-failure__text">
        <strong>{title}</strong>
        <span>{children}</span>
      </div>
      {actions}
    </div>
  )
}

export type ItemState = 'done' | 'working' | 'failed'

/** An item line "7b": a file taken in, or (`dense`) a chapter being read, with its mono count. */
export function ItemLine({
  state,
  children,
  detail,
  dense = false,
}: {
  state: ItemState
  children: ReactNode
  detail: ReactNode
  dense?: boolean
}) {
  return (
    <div className={`ema-item-line ema-item-line--${state} ${dense ? 'ema-item-line--dense' : ''}`}>
      <span className="ema-item-line__mark">
        {state === 'done' && <Icon icon={Check} size={13} stroke={2.6} color="var(--olive-mark)" />}
        {state === 'working' && <span className="ema-spinner ema-spinner--11" />}
        {state === 'failed' && <span className="ema-dot ema-dot--err" />}
      </span>
      <span className="ema-item-line__label">{children}</span>
      <span className="ema-item-line__detail">{detail}</span>
    </div>
  )
}
