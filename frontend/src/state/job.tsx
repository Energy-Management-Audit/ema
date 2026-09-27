// The open job's shared reads and its run (D4). Every tab gets job, client, checks, outputs,
// summary and the log from here; a run's terminal event refetches what it can change.

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api } from '../api/endpoints.ts'
import { subscribeRun } from '../api/events.ts'
import type {
  Client,
  Decision,
  ExportChecks,
  Field,
  Job,
  JobStatus,
  Output,
  PieeSummary,
} from '../api/types.ts'
import { invalidate, invalidateJob, jobKey, useResource, type Resource } from './resource.ts'
import { TERMINAL, runReducer, startRun, type RunState } from './run.ts'

const TERMINAL_KEYS = [
  'job',
  'status',
  'outputs',
  'fields',
  'missing',
  'checks',
  'summary',
  'log',
  'prelucrare',
  'slots',
]

export type JobContextValue = {
  jobId: string
  job: Resource<Job>
  client: Resource<Client>
  checks: Resource<ExportChecks>
  outputs: Resource<Output[]>
  summary: Resource<PieeSummary>
  log: Resource<Decision[]>
  fields: Resource<Field[]>
  status: Resource<JobStatus>
  run: RunState | null
  runError: unknown
  follow: (runId: string, stage: string) => void
  refresh: (...names: string[]) => void
}

const JobContext = createContext<JobContextValue | null>(null)

export function useJob(): JobContextValue {
  const value = useContext(JobContext)
  if (!value) throw new Error('useJob outside JobProvider')
  return value
}

export function JobProvider({ jobId, children }: { jobId: string; children: ReactNode }) {
  const job = useResource(jobKey(jobId, 'job'), () => api.job(jobId))
  const clientSlug = job.data?.client_slug ?? null
  const client = useResource(clientSlug ? `client/${clientSlug}` : null, () =>
    api.client(clientSlug ?? ''),
  )
  const checks = useResource(jobKey(jobId, 'checks'), () => api.checks(jobId))
  const outputs = useResource(jobKey(jobId, 'outputs'), () => api.outputs(jobId))
  const summary = useResource(job.data?.type === 'piee' ? jobKey(jobId, 'summary') : null, () =>
    api.summary(jobId),
  )
  const log = useResource(jobKey(jobId, 'log'), () => api.log(jobId))
  const fields = useResource(jobKey(jobId, 'fields'), () => api.fields(jobId))
  const status = useResource(jobKey(jobId, 'status'), () => api.status(jobId))
  const [started, setStarted] = useState<{ runId: string; stage: string } | null>(null)
  const [progress, setProgress] = useState<RunState | null>(null)
  const [runError, setRunError] = useState<unknown>(null)

  const refresh = useCallback(
    (...names: string[]) => {
      invalidateJob(jobId, ...names)
    },
    [jobId],
  )

  const follow = useCallback((runId: string, stage: string) => {
    setRunError(null)
    setStarted({ runId, stage })
  }, [])

  // A run started elsewhere (or before a reload) replays its progress from the stream.
  const running = status.data?.runs.find((item) => item.state === 'running')
  const target = running ? { runId: running.id, stage: running.stage } : started
  const run = target
    ? progress?.runId === target.runId
      ? progress
      : startRun(target.runId, target.stage)
    : null
  const targetId = target?.runId
  const targetStage = target?.stage ?? ''
  useEffect(() => {
    if (!targetId) return
    let state = startRun(targetId, targetStage)
    return subscribeRun(
      jobId,
      targetId,
      (event) => {
        state = runReducer(state, event)
        setProgress(state)
        if (TERMINAL.has(event.type)) {
          invalidateJob(jobId, ...TERMINAL_KEYS)
          invalidate('overview')
        }
      },
      (error) => {
        setRunError(error)
      },
    )
  }, [jobId, targetId, targetStage])

  useEffect(() => {
    const onFocus = () => {
      invalidateJob(jobId, 'job', 'checks')
    }
    window.addEventListener('focus', onFocus)
    return () => {
      window.removeEventListener('focus', onFocus)
    }
  }, [jobId])

  return (
    <JobContext.Provider
      value={{
        jobId,
        job,
        client,
        checks,
        outputs,
        summary,
        log,
        fields,
        status,
        run,
        runError,
        follow,
        refresh,
      }}
    >
      {children}
    </JobContext.Provider>
  )
}
