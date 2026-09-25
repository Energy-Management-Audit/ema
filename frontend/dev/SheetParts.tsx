import type { ReactNode } from 'react'

export type Theme = 'light' | 'dark'

export function SheetFrame({
  id,
  theme,
  children,
}: {
  id: string
  theme: Theme
  children: ReactNode
}) {
  return (
    <div id={id} className="sheet-frame" data-theme={theme}>
      {children}
    </div>
  )
}

/** One row of the sheet: the mono label (and, for extensions, the design ids it reproduces). */
export function SheetRow({
  label,
  refs,
  wide = false,
  children,
}: {
  label: string
  refs?: string
  wide?: boolean
  children: ReactNode
}) {
  return (
    <div className={`sheet-row ${wide ? 'sheet-row--wide' : ''}`} data-refs={refs}>
      <span className="sheet-row__label">
        {label}
        {refs && <span className="sheet-row__ref">{refs}</span>}
      </span>
      <div className="sheet-row__body">{children}</div>
    </div>
  )
}

export function Legend({ children, small = false }: { children: ReactNode; small?: boolean }) {
  return <span className={`sheet-legend ${small ? 'sheet-legend--small' : ''}`}>{children}</span>
}

export function Swatch({
  color,
  hex,
  name,
  ring = true,
}: {
  color: string
  hex: string
  name: string
  ring?: boolean
}) {
  return (
    <span className="sheet-swatch">
      <span
        className="sheet-swatch__dot"
        style={{
          background: color,
          boxShadow: ring ? 'inset 0 0 0 1px var(--swatch-ring)' : undefined,
        }}
      />
      <span className="sheet-swatch__text">
        <span>{hex}</span>
        <span>{name}</span>
      </span>
    </span>
  )
}

/** The README token table: name, light, dark. */
export const tokenTable: [name: string, light: string, dark: string][] = [
  ['surface', '#f6f2e8', '#1e1b16'],
  ['surface-sunken', '#f0ebde', '#181510'],
  ['surface-raised', '#f1ecdf', '#242019'],
  ['surface-accent', '#f3ead6', '#2a2419'],
  ['paper', '#fffdf6', '#fffdf6'],
  ['ink', '#252219', '#ece5d5'],
  ['ink-muted', 'rgba(37,34,25,.72)', 'rgba(236,229,213,.72)'],
  ['border', 'rgba(37,34,25,.11)', 'rgba(236,229,213,.11)'],
  ['olive', '#4f7015', '#9bbb52'],
  ['amber', '#b8751a', '#d8a24e'],
  ['error', '#9e3f1f', '#e8836a'],
  ['violet', '#7a5ea8', '#a58cd4'],
]

function TokenValue({ value, ring }: { value: string; ring: string }) {
  return (
    <span className="sheet-tokens__value">
      <span
        className="sheet-tokens__dot"
        style={{ background: value, boxShadow: `inset 0 0 0 1px ${ring}` }}
      />
      {value}
    </span>
  )
}

export function TokenTable({ theme }: { theme: Theme }) {
  const lightRing = theme === 'dark' ? 'rgba(236,229,213,.3)' : 'rgba(37,34,25,.14)'
  return (
    <div className="sheet-tokens">
      <div className="sheet-tokens__row sheet-tokens__row--head">
        <span>NUME</span>
        <span>CLAR</span>
        <span>ÎNTUNECAT</span>
      </div>
      {tokenTable.map(([name, light, dark]) => (
        <div key={name} className="sheet-tokens__row">
          <span>{name}</span>
          <TokenValue value={light} ring={lightRing} />
          <TokenValue
            value={dark}
            ring={theme === 'dark' && name === 'paper' ? 'rgba(37,34,25,.3)' : lightRing}
          />
        </div>
      ))}
      <span className="sheet-tokens__note">
        paper nu se inversează: paginile de document rămân albe în ambele teme.
      </span>
    </div>
  )
}
