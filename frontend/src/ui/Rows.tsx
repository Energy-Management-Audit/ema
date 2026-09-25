import type { CSSProperties, HTMLAttributes, ReactNode } from 'react'
import './rows.css'

/** Table row "7d" (RÂND TABEL): hairline separator; hover gets the 5 % fill and r10. */
export function TableRow({ children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className="ema-table-row" role="row" {...rest}>
      {children}
    </div>
  )
}

/** A cell of a table row: `grow` for the name column, a fixed width for figures (Geist Mono,
 * right-aligned). */
export function Cell({
  children,
  width,
  grow = false,
  figures = false,
  end = false,
}: {
  children: ReactNode
  width?: number
  grow?: boolean
  figures?: boolean
  end?: boolean
}) {
  const style: CSSProperties = grow ? { flex: 1, minWidth: 0 } : { flex: `0 0 ${String(width)}px` }
  return (
    <span
      role="cell"
      className={`ema-cell ${grow ? 'ema-cell--name' : ''} ${figures ? 'ema-cell--figures' : ''} ${end ? 'ema-cell--end' : ''}`}
      style={style}
    >
      {children}
    </span>
  )
}

/** List row "7d" (STĂRI RÂND): transparent, hover 5 %, selected olive 12 % with a 2px bar on
 * the left. `boxed` is the sunken r12 row of 7c (and of the FOCUS specimen). */
export function ListRow({
  children,
  selected = false,
  boxed = false,
  className,
  ...rest
}: HTMLAttributes<HTMLDivElement> & { selected?: boolean; boxed?: boolean }) {
  return (
    <div
      className={`ema-list-row ${boxed ? 'ema-list-row--boxed' : ''} ${className ?? ''}`}
      aria-selected={selected}
      {...rest}
    >
      {children}
    </div>
  )
}
