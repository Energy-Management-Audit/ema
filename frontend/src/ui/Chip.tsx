import type { ReactNode } from 'react'
import { Calculator, Check, Clock, File, Globe, Ban, Pencil, X } from 'lucide-react'
import { Icon } from './Icon'
import './chip.css'

export type Tone = 'ok' | 'warn' | 'err' | 'muted'

function Dot({ tone }: { tone: Tone }) {
  return <span className={`ema-dot ema-dot--${tone}`} aria-hidden />
}

/** Label "7d" (ETICHETE): confirmat, de verificat, eşuat. */
export function StatusChip({
  tone,
  children,
}: {
  tone: 'ok' | 'warn' | 'err'
  children: ReactNode
}) {
  return (
    <span className={`ema-status-chip ema-status-chip--${tone}`}>
      {tone === 'ok' ? (
        <Icon icon={Check} size={13} stroke={2.6} color="var(--olive-mark)" />
      ) : (
        <Dot tone={tone} />
      )}
      {children}
    </span>
  )
}

/** Label "7d" câmp lipsă: a missing value, clickable to fill it in. */
export function MissingChip({ children, onClick }: { children: ReactNode; onClick?: () => void }) {
  return (
    <button type="button" className="ema-status-chip ema-status-chip--missing" onClick={onClick}>
      {children}
    </button>
  )
}

/** Label "7d" pag. 44: the page reference, in mono. */
export function PageChip({ children }: { children: ReactNode }) {
  return <span className="ema-page-chip">{children}</span>
}

export type SourceKind = 'document' | 'online' | 'calculated' | 'manual'

const sourceIcons = { document: File, online: Globe, calculated: Calculator, manual: Pencil }

/** Source chip "M5": where a fact came from. Document (page or cell), online (domain + date,
 * green outline), calculated (dashed outline), manual (pencil; label „introdus manual”). */
export function SourceChip({
  kind,
  children,
  onClick,
}: {
  kind: SourceKind
  children: ReactNode
  onClick?: () => void
}) {
  return (
    <button type="button" className={`ema-source-chip ema-source-chip--${kind}`} onClick={onClick}>
      <Icon icon={sourceIcons[kind]} size={13} stroke={1.7} />
      {children}
    </button>
  )
}

export type StatusMark = 'dot' | 'none' | 'accepted' | 'rejected' | 'working' | 'later' | 'na'

/** Inline status "7d/3j/M8" (mono, 11px): complet, lipseşte, the review outcomes of 3c,
 * „mai târziu” with its reason (clock) and „nu se aplică” (ban). */
export function Status({
  tone,
  mark = 'dot',
  children,
}: {
  tone: Tone
  mark?: StatusMark
  children: ReactNode
}) {
  return (
    <span className={`ema-status ema-status--${tone}`}>
      {mark === 'dot' && <Dot tone={tone} />}
      {mark === 'accepted' && (
        <Icon icon={Check} size={11} stroke={2.6} color="var(--olive-mark)" />
      )}
      {mark === 'rejected' && <Icon icon={X} size={11} stroke={2.2} />}
      {mark === 'working' && <span className="ema-spinner ema-spinner--11" aria-hidden />}
      {mark === 'later' && <Icon icon={Clock} size={12} stroke={1.8} />}
      {mark === 'na' && <Icon icon={Ban} size={12} stroke={1.8} />}
      {children}
    </span>
  )
}

/** Tag "3i" IMPLICIT. */
export function Tag({ children }: { children: ReactNode }) {
  return <span className="ema-tag">{children}</span>
}

/** Spinner "3c/7b": a hairline ring with an olive head. */
export function Spinner({ size = 11 }: { size?: 10 | 11 }) {
  return (
    <span
      className={`ema-spinner ema-spinner--${String(size)}`}
      role="status"
      aria-label="în lucru"
    />
  )
}
