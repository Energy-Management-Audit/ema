import type { ReactNode } from 'react'
import './nav.css'

export type TabItem = { id: string; label: ReactNode; count?: ReactNode; pending?: boolean }

/** Tabs "3c": 13.5px, the active one at 600 with a 1.5px ink underline; counts in the label,
 * amber when something waits. `aside` holds the right-aligned filters. */
export function Tabs({
  items,
  active,
  onSelect,
  aside,
}: {
  items: TabItem[]
  active: string
  onSelect: (id: string) => void
  aside?: ReactNode
}) {
  return (
    <div className="ema-tabs">
      <div className="ema-tabs__list" role="tablist">
        {items.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={tab.id === active}
            className="ema-tabs__tab"
            onClick={() => {
              onSelect(tab.id)
            }}
          >
            {tab.label}
            {tab.count !== undefined && (
              <span className={tab.pending ? 'ema-tabs__count--pending' : 'ema-tabs__count'}>
                {tab.count}
              </span>
            )}
          </button>
        ))}
        {aside && <span className="ema-tabs__aside">{aside}</span>}
      </div>
      <div className="ema-tabs__rule" />
    </div>
  )
}

export type StepState = 'done' | 'warn' | 'current' | 'todo'
export type Step = {
  label: string
  detail: string
  state: StepState
  tone?: 'ok' | 'warn' | 'muted'
}

/** Stepper "3c": the job's stages on a hairline track; done olive, waiting amber, the current
 * stage a ringed pulse, the rest hollow. `progress` is how far the olive track runs. */
export function Stepper({ steps, progress }: { steps: Step[]; progress: number }) {
  return (
    <div className="ema-stepper">
      <div className="ema-stepper__track">
        <span className="ema-stepper__rail" />
        <span className="ema-stepper__fill" style={{ width: `${String(progress)}%` }} />
        {steps.map((step, index) => (
          <span
            key={step.label}
            className={`ema-stepper__slot ${index === steps.length - 1 ? 'ema-stepper__slot--last' : ''}`}
          >
            <span className={`ema-stepper__dot ema-stepper__dot--${step.state}`}>
              {step.state === 'current' && <span className="ema-stepper__pulse" />}
            </span>
          </span>
        ))}
      </div>
      <ol className="ema-stepper__labels">
        {steps.map((step, index) => (
          <li
            key={step.label}
            className={`ema-stepper__slot ${index === steps.length - 1 ? 'ema-stepper__slot--last' : ''}`}
            aria-current={step.state === 'current' ? 'step' : undefined}
          >
            <span className="ema-stepper__label">{step.label}</span>
            <span className={`ema-stepper__detail ema-stepper__detail--${step.tone ?? 'muted'}`}>
              {step.detail}
            </span>
          </li>
        ))}
      </ol>
    </div>
  )
}
