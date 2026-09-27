import { useState } from 'react'
import { api } from '../../api/endpoints.ts'
import type { AuditOutline } from '../../api/audit-types.ts'
import type { Decision, Field } from '../../api/types.ts'
import { scalar } from '../../audit/review.ts'
import { decisionLabel } from '../../audit/journal.ts'
import { plural } from '../../audit/plural.ts'
import { rel } from '../../lib/format.ts'
import { useJob } from '../../state/job.tsx'
import { invalidate } from '../../state/resource.ts'
import { ActivityEntry } from '../../ui/Activity.tsx'
import { ProgressBar } from '../../ui/Feedback.tsx'
import { SectionKey } from '../../ui/Surface.tsx'

export function ReviewActivity({ fields, outline }: { fields: Field[]; outline: AuditOutline }) {
  const ctx = useJob()
  const [problem, setProblem] = useState<string | null>(null)
  const names = new Map([
    ...fields.map((field) => [field.id, field.label] as const),
    ...outline.nodes.map((node) => [node.id, node.title] as const),
  ])
  const decisions = [...(ctx.log.data ?? [])].reverse().filter((decision) => !decision.undone_by)
  const seen = new Set<string>()
  const entries = decisions
    .filter((decision) => {
      if (!decision.batch_id) return true
      if (seen.has(decision.batch_id)) return false
      seen.add(decision.batch_id)
      return true
    })
    .slice(0, 6)
  const accepted = fields.filter(
    (field) => field.review === 'accepted' || field.review === 'corrected',
  ).length
  const waiting = fields.filter((field) => field.review === 'pending').length
  const undo = async (items: Decision[]) => {
    setProblem(null)
    for (const item of items) {
      try {
        await api.undo(ctx.jobId, item.id)
      } catch (error) {
        setProblem(
          `${names.get(item.field_id) ?? item.field_id}: ${error instanceof Error ? error.message : 'Nu se poate anula.'}`,
        )
        break
      }
    }
    ctx.refresh('fields', 'outline', 'checks', 'log')
    invalidate('overview')
  }
  return (
    <div className="audit-review-activity">
      {problem && (
        <p role="alert" className="audit-error">
          {problem}
        </p>
      )}
      {entries.map((decision) => {
        const batch = decision.batch_id
          ? decisions.filter((item) => item.batch_id === decision.batch_id)
          : [decision]
        const chapter = fields
          .find((field) => field.id === decision.field_id)
          ?.chapter?.match(/ch(\d+)/)?.[1]
        const before = decision.before.value
        const after = decision.after.value
        const detail = decision.batch_id
          ? `acceptate toate deodată${chapter ? ` · cap. ${chapter}` : ''}`
          : decision.action === 'correct'
            ? `${scalar(before)} → ${scalar(after)}, scris de tine`
            : decision.action === 'accept'
              ? `acceptat${chapter ? `, scris la ${chapter}` : ''}`
              : decision.action === 'reject'
                ? 'respins'
                : decision.action === 'status'
                  ? decisionLabel(decision)
                  : 'aleasă o valoare'
        return (
          <ActivityEntry
            key={decision.id}
            outcome={decision.action === 'reject' ? 'rejected' : 'accepted'}
            title={names.get(decision.field_id) ?? decision.field_id}
            detail={detail}
            time={rel(decision.at)}
            undo={
              decision.action === 'undo'
                ? undefined
                : decision.batch_id
                  ? 'Anulează toate'
                  : 'Anulează'
            }
            onUndo={() => void undo(batch)}
          />
        )
      })}
      <div className="audit-activity-footer">
        <SectionKey>CÂT A MAI RĂMAS</SectionKey>
        <strong>
          {accepted}/{fields.length}
        </strong>
        <ProgressBar value={fields.length ? Math.round((accepted / fields.length) * 100) : 0} />
        <small>
          {waiting
            ? `Raportul se poate genera după ${plural(waiting, 'ultimul câmp', 'ultimele câmpuri')}.`
            : 'Nimic nu mai aşteaptă revizuirea.'}
        </small>
      </div>
    </div>
  )
}
