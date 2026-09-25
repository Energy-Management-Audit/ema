import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Check } from 'lucide-react'
import { Icon } from './Icon'
import './dialog.css'

export function nextFocusIndex(count: number, current: number, backwards: boolean): number {
  if (count < 1) return -1
  if (current < 0) return backwards ? count - 1 : 0
  return (current + (backwards ? count - 1 : 1)) % count
}

/** Dialog "7c", only for consequential actions: the title states the action, the body what is
 * lost in concrete numbers, the primary button carries the action's name. Red only on delete. */
export function Dialog({
  title,
  children,
  content,
  actions,
  onClose,
}: {
  title: ReactNode
  children: ReactNode
  content?: ReactNode
  actions: ReactNode
  onClose: () => void
}) {
  const titleId = useId()
  const dialogRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const previousFocus =
      document.activeElement instanceof HTMLElement ? document.activeElement : null
    const root = document.getElementById('root')
    const wasInert = root?.inert ?? false
    if (root) root.inert = true
    const dialog = dialogRef.current
    if (dialog) {
      const controls = getFocusable(dialog)
      ;(controls[0] ?? dialog).focus()
    }
    return () => {
      if (root) root.inert = wasInert
      previousFocus?.focus()
    }
  }, [])

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') {
      event.preventDefault()
      onClose()
      return
    }
    if (event.key !== 'Tab' || !dialogRef.current) return
    const controls = getFocusable(dialogRef.current)
    if (controls.length === 0) {
      event.preventDefault()
      dialogRef.current.focus()
      return
    }
    const current = controls.indexOf(document.activeElement as HTMLElement)
    const next = nextFocusIndex(controls.length, current, event.shiftKey)
    if (current < 0 || (event.shiftKey ? current === 0 : current === controls.length - 1)) {
      event.preventDefault()
      controls[next]?.focus()
    }
  }

  return createPortal(
    <div className="ema-dialog-backdrop">
      <div
        ref={dialogRef}
        className="ema-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onKeyDown={handleKeyDown}
      >
        <div className="ema-dialog__head">
          <h3 id={titleId}>{title}</h3>
          <p>{children}</p>
        </div>
        <div className="ema-dialog__content">
          {content}
          <div className="ema-dialog__actions">{actions}</div>
        </div>
      </div>
    </div>,
    document.body,
  )
}

function getFocusable(dialog: HTMLDivElement | null): HTMLElement[] {
  return dialog
    ? Array.from(
        dialog.querySelectorAll<HTMLElement>(
          'a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])',
        ),
      )
    : []
}

/** Checkbox row "7c": the sunken r12 row with a 15px box. */
export function CheckRow({
  checked,
  onChange,
  children,
}: {
  checked: boolean
  onChange: (next: boolean) => void
  children: ReactNode
}) {
  return (
    <label className="ema-check-row">
      <input
        type="checkbox"
        className="ema-check-row__box"
        checked={checked}
        onChange={(event) => {
          onChange(event.target.checked)
        }}
      />
      {children}
    </label>
  )
}

/** Choice "7c": one of the exclusive options of a dialog; the chosen one is sunken with an
 * olive inset and a filled check. */
export function Choice({
  name,
  checked,
  onSelect,
  title,
  detail,
}: {
  name: string
  checked: boolean
  onSelect: () => void
  title: ReactNode
  detail: ReactNode
}) {
  return (
    <label className="ema-choice" data-checked={checked || undefined}>
      <input
        type="radio"
        name={name}
        checked={checked}
        onChange={onSelect}
        className="ema-visually-hidden"
      />
      <span className="ema-choice__radio" aria-hidden>
        {checked && <Icon icon={Check} size={10} stroke={3.4} />}
      </span>
      <span className="ema-choice__text">
        <strong>{title}</strong>
        <span>{detail}</span>
      </span>
    </label>
  )
}

/** File notice "7c": the amber row naming the file an action would overwrite. */
export function FileNotice({ name, detail }: { name: ReactNode; detail: ReactNode }) {
  return (
    <div className="ema-file-notice">
      <span className="ema-dot ema-dot--warn" />
      <span className="ema-file-notice__name">{name}</span>
      <span className="ema-file-notice__detail">{detail}</span>
    </div>
  )
}
