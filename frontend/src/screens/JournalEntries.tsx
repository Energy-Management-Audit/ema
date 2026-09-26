import type { Decision } from '../api/types.ts'
import { api } from '../api/endpoints.ts'
import { rel } from '../lib/format.ts'
import { journalLine, newestFirst } from '../piee/journal.ts'
import { useJob } from '../state/job.tsx'
import { ActivityEntry } from '../ui/Activity'
import { ProblemNotice, STALE_CODES, useAction } from './actions.tsx'

export const DECISION_KEYS = ['fields', 'missing', 'checks', 'summary', 'log']

/** Jurnal entries, newest first, each undoable once (3c). */
export function JournalEntries({
  filter,
  max,
}: {
  filter?: (decision: Decision) => boolean
  max?: number
}) {
  const ctx = useJob()
  const undo = useAction()
  const year = ctx.job.data?.year ?? null
  const all = newestFirst(ctx.log.data ?? []).filter((item) => (filter ? filter(item) : true))
  const shown = max === undefined ? all : all.slice(0, max)
  return (
    <>
      <ProblemNotice problem={undo.problem} />
      {shown.map((decision) => {
        const line = journalLine(decision, year)
        return (
          <ActivityEntry
            key={decision.id}
            testId={`journal-entry-${decision.id}`}
            outcome={line.outcome}
            title={line.title}
            time={rel(decision.at)}
            detail={line.detail}
            undo={line.undoable ? 'Anulează' : undefined}
            onUndo={() => {
              void undo.run(
                async () => {
                  await api.undo(ctx.jobId, decision.id)
                  ctx.refresh(...DECISION_KEYS)
                },
                (problem) => {
                  if (STALE_CODES.has(problem.code)) ctx.refresh(...DECISION_KEYS)
                },
              )
            }}
          />
        )
      })}
    </>
  )
}

export function isMeasureDecision(decision: Decision): boolean {
  const key = decision.after.key ?? decision.before.key
  return typeof key === 'string' && key.startsWith('measure.')
}
