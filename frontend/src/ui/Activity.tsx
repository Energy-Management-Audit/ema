import type { ReactNode } from 'react'
import { Check, PanelRight, X } from 'lucide-react'
import { Button, IconButton } from './Button'
import { Icon } from './Icon'
import './shell.css'

/** Activity panel "3c" (290): what happened, newest first, each entry undoable; a footer with
 * what is left. */
export function ActivityPanel({
  title,
  children,
  footer,
  onAll,
}: {
  title: ReactNode
  children: ReactNode
  footer?: ReactNode
  onAll?: () => void
}) {
  return (
    <aside className="ema-activity">
      <div className="ema-activity__head">
        <span className="ema-activity__title">{title}</span>
        <Button variant="quiet" height={26} className="ema-activity__all" onClick={onAll}>
          Tot jurnalul
        </Button>
        <IconButton
          icon={PanelRight}
          label="Restrânge panoul"
          size={28}
          iconSize={16}
          bordered={false}
        />
      </div>
      <div className="ema-activity__list">{children}</div>
      {footer && <div className="ema-activity__footer">{footer}</div>}
    </aside>
  )
}

/** An activity entry "3c": the outcome mark, the field, when, what changed and the undo. */
export function ActivityEntry({
  outcome,
  title,
  time,
  detail,
  undo,
  onUndo,
  testId,
}: {
  outcome: 'accepted' | 'rejected' | 'info'
  title: ReactNode
  time: ReactNode
  detail?: ReactNode
  undo?: string
  onUndo?: () => void
  testId?: string
}) {
  return (
    <div className={`ema-activity-entry ema-activity-entry--${outcome}`} data-testid={testId}>
      <div className="ema-activity-entry__line">
        {outcome === 'accepted' && (
          <Icon icon={Check} size={12} stroke={2.6} color="var(--olive-mark)" />
        )}
        {outcome === 'rejected' && (
          <Icon icon={X} size={12} stroke={2.2} color="var(--error-ink)" />
        )}
        {outcome === 'info' && <span className="ema-activity-entry__bullet">·</span>}
        <span className="ema-activity-entry__title">{title}</span>
        <span className="ema-activity-entry__time">{time}</span>
      </div>
      {detail && <span className="ema-activity-entry__detail">{detail}</span>}
      {undo && (
        <Button
          variant="secondary"
          height={26}
          className="ema-activity-entry__undo"
          onClick={onUndo}
        >
          {undo}
        </Button>
      )}
    </div>
  )
}
