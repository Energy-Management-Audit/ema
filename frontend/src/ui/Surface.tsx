import type { CSSProperties, ReactNode } from 'react'
import './surface.css'

/** Brand mark "3c": the lowercase e on olive; the notched corner is the logo. 24 in the
 * sidebar, 30 in the Ema widget, 38 on the empty state (7b). */
export function BrandMark({ size = 24 }: { size?: 24 | 30 | 38 }) {
  return (
    <span className={`ema-mark ema-mark--${String(size)}`} aria-hidden>
      e
    </span>
  )
}

/** Group box "3i": raised surface, hairline, r16; rows separated by a hairline. */
export function GroupBox({ children }: { children: ReactNode }) {
  return <div className="ema-group">{children}</div>
}

/** A row of a group box "3i": title (+ tag), the explanation line, an optional state line,
 * and the control on the right. */
export function GroupRow({
  title,
  tag,
  description,
  state,
  control,
}: {
  title: ReactNode
  tag?: ReactNode
  description: ReactNode
  state?: ReactNode
  control: ReactNode
}) {
  return (
    <div className="ema-group__row">
      <div className="ema-group__text">
        <div className="ema-group__title">
          <span>{title}</span>
          {tag}
        </div>
        <span className="ema-group__description">{description}</span>
        {state && <span className="ema-group__state">{state}</span>}
      </div>
      <div className="ema-group__control">{control}</div>
    </div>
  )
}

/** Card "7b": the state panels, surface with a hairline and the soft card shadow. */
export function Card({
  children,
  height,
  style,
}: {
  children: ReactNode
  height?: number
  style?: CSSProperties
}) {
  return (
    <div className="ema-card" style={{ height, ...style }}>
      {children}
    </div>
  )
}

/** Card header "7b": title, a mono count, and an optional right-aligned note. */
export function CardHeader({
  title,
  count,
  aside,
}: {
  title: ReactNode
  count?: ReactNode
  aside?: ReactNode
}) {
  return (
    <div className="ema-card__header">
      <span className="ema-card__title">{title}</span>
      {count && <span className="ema-card__count">{count}</span>}
      {aside && <span className="ema-card__aside">{aside}</span>}
    </div>
  )
}

/** Paper "7d": a document surface. Never inverts: it resets the light palette for everything
 * inside it, in both themes. */
export function Paper({
  children,
  className,
  style,
}: {
  children: ReactNode
  className?: string
  style?: CSSProperties
}) {
  return (
    <div className={`ema-paper ema-paper-sheet ${className ?? ''}`} style={style}>
      {children}
    </div>
  )
}

/** Section key "7d" (ANTET SECŢIUNE): 11px, .09em, uppercase, muted. */
export function SectionKey({ children }: { children: ReactNode }) {
  return <span className="ema-section-key">{children}</span>
}
