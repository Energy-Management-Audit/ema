// Pure run progress state, folded from the job's server-sent events (D4).

import type { JobEvent } from '../api/types.ts'

export type RunState = {
  runId: string
  stage: string
  state: 'running' | 'ready' | 'failed' | 'cancelled'
  done: number
  total: number
  message: string
  startedAt: string | null
  publication: string | null
  itemFailures: number
  steps: { message: string; done: number | null; total: number | null; at: string }[]
}

export const TERMINAL = new Set(['stage_finished', 'stage_failed', 'stage_cancelled'])

export function startRun(runId: string, stage: string): RunState {
  return {
    runId,
    stage,
    state: 'running',
    done: 0,
    total: 0,
    message: '',
    startedAt: null,
    publication: null,
    itemFailures: 0,
    steps: [],
  }
}

export function runReducer(state: RunState, event: JobEvent): RunState {
  if (event.run_id !== state.runId) return state
  const payload = event.payload
  switch (event.type) {
    case 'stage_started':
      return { ...state, stage: event.stage, state: 'running', startedAt: event.at }
    case 'stage_progress':
      return {
        ...state,
        done: typeof payload.done === 'number' ? payload.done : state.done,
        total: typeof payload.total === 'number' ? payload.total : state.total,
        message: typeof payload.message === 'string' ? payload.message : state.message,
        steps:
          typeof payload.message === 'string' && payload.message.trim()
            ? [
                ...state.steps,
                {
                  message: payload.message,
                  done: typeof payload.done === 'number' ? payload.done : null,
                  total: typeof payload.total === 'number' ? payload.total : null,
                  at: event.at,
                },
              ].slice(-20)
            : state.steps,
      }
    case 'item_failed':
      return { ...state, itemFailures: state.itemFailures + 1 }
    case 'stage_finished':
      return {
        ...state,
        state: 'ready',
        publication: typeof payload.publication === 'string' ? payload.publication : null,
      }
    case 'stage_failed':
      return { ...state, state: 'failed' }
    case 'stage_cancelled':
      return { ...state, state: 'cancelled' }
    default:
      return state
  }
}

/** The terminal event a closed stream never delivered, rebuilt from the run's stored state. */
export function terminalFor(state: RunState, runState: string): JobEvent | null {
  const type =
    runState === 'ready'
      ? 'stage_finished'
      : runState === 'failed'
        ? 'stage_failed'
        : runState === 'cancelled'
          ? 'stage_cancelled'
          : null
  if (type === null) return null
  return {
    seq: 0,
    job_id: '',
    run_id: state.runId,
    stage: state.stage,
    type,
    at: new Date().toISOString(),
    payload: { state: runState },
  }
}
