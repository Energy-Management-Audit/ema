import { useEffect, useState } from 'react'
import type { RunState } from '../../state/run.ts'
import { Button } from '../../ui/Button.tsx'
import { SectionKey } from '../../ui/Surface.tsx'

function elapsed(startedAt: string | null, now: number): string | null {
  if (!startedAt) return null
  const seconds = Math.max(0, Math.floor((now - Date.parse(startedAt)) / 1000))
  if (!Number.isFinite(seconds)) return null
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
}

export function RunActivity({ run, onStop }: { run: RunState; onStop: () => void }) {
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    const timer = window.setInterval(() => {
      setNow(Date.now())
    }, 1000)
    return () => {
      window.clearInterval(timer)
    }
  }, [])
  return (
    <div className="audit-run">
      <div className="audit-run__head">
        <strong>Se lucrează</strong>
        {elapsed(run.startedAt, now) && <time>{elapsed(run.startedAt, now)}</time>}
      </div>
      <SectionKey>PAŞII DE PÂNĂ ACUM</SectionKey>
      <ol className="audit-run__steps">
        {run.steps.slice(-5).map((step, index) => (
          <li key={`${step.at}-${String(index)}`}>
            <span>{step.message}</span>
            {step.total !== null && step.total > 0 && step.done !== null && (
              <small>
                {step.done}/{step.total}
              </small>
            )}
          </li>
        ))}
      </ol>
      {run.steps.length === 0 && <p>Se pregăteşte etapa…</p>}
      <Button variant="secondary" height={26} onClick={onStop}>
        Opreşte
      </Button>
    </div>
  )
}
