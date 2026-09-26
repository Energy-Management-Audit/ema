// One run's progress over the job's event stream (D4). Other runs' events are dropped; the stream
// closes after that run's terminal event. A stream closed early is reconciled with one status read.

import { api, eventsPath } from './endpoints.ts'
import type { JobEvent } from './types.ts'
import { TERMINAL, startRun, terminalFor } from '../state/run.ts'

const TYPES = [
  'stage_started',
  'stage_progress',
  'stage_finished',
  'stage_failed',
  'stage_cancelled',
  'item_failed',
]

export function subscribeRun(
  jobId: string,
  runId: string,
  onEvent: (event: JobEvent) => void,
  onError: (error: unknown) => void,
): () => void {
  let source: EventSource | null = null
  let stopped = false

  const finish = () => {
    stopped = true
    source?.close()
  }

  const reconcile = async () => {
    const status = await api.status(jobId)
    if (stopped) return
    const run = status.runs.find((item) => item.id === runId)
    if (!run || run.state === 'running') {
      open()
      return
    }
    const event = terminalFor(startRun(runId, run.stage), run.state)
    finish()
    if (event) onEvent(event)
  }

  const open = () => {
    source = new EventSource(eventsPath(jobId))
    const current = source
    const handle = (message: MessageEvent<string>) => {
      const event = JSON.parse(message.data) as JobEvent
      if (event.run_id !== runId) return
      onEvent(event)
      if (TERMINAL.has(event.type)) finish()
    }
    for (const type of TYPES) current.addEventListener(type, handle as EventListener)
    current.onerror = () => {
      if (stopped || current.readyState !== EventSource.CLOSED) return
      void reconcile().catch((error: unknown) => {
        finish()
        onError(error)
      })
    }
  }

  open()
  return finish
}
