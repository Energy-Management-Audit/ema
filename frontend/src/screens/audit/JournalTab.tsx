import { useState } from 'react'
import { api } from '../../api/endpoints.ts'
import type { AuditOutline } from '../../api/audit-types.ts'
import { decisionLabel } from '../../audit/journal.ts'
import { rel } from '../../lib/format.ts'
import { useJob } from '../../state/job.tsx'
import { invalidate } from '../../state/resource.ts'
import { ActivityEntry } from '../../ui/Activity.tsx'
import { Button } from '../../ui/Button.tsx'
import { SectionKey } from '../../ui/Surface.tsx'

export function JournalTab({ outline }: { outline: AuditOutline }) {
  const ctx = useJob()
  const [problem, setProblem] = useState<string | null>(null)
  const decisions = [...(ctx.log.data ?? [])].reverse()
  const undo = async (id: string) => {
    try {
      await api.undo(ctx.jobId, id)
      ctx.refresh('fields', 'outline', 'checks', 'log')
      invalidate('overview')
      setProblem(null)
    } catch (error) {
      setProblem(error instanceof Error ? error.message : 'Decizia nu se poate anula.')
    }
  }
  const names = new Map(outline.nodes.map((node) => [node.id, node.title]))
  const fields = new Map((ctx.fields.data ?? []).map((field) => [field.id, field.label]))
  return (
    <div className="audit-journal">
      <SectionKey>Jurnal</SectionKey>
      {decisions.length === 0 && <p>Nu există decizii încă.</p>}
      {problem && (
        <p className="audit-error" role="alert">
          {problem}
        </p>
      )}
      {decisions.map((decision) => (
        <ActivityEntry
          key={decision.id}
          outcome={decision.action === 'reject' ? 'rejected' : 'accepted'}
          title={names.get(decision.field_id) ?? fields.get(decision.field_id) ?? decision.field_id}
          detail={decisionLabel(decision)}
          time={rel(decision.at)}
          undo={!decision.undone_by && decision.action !== 'undo' ? 'Anulează' : undefined}
          onUndo={() => void undo(decision.id)}
        />
      ))}
      {decisions.some((decision) => decision.batch_id) && (
        <Button
          variant="secondary"
          height={30}
          onClick={() => {
            const batch = decisions.find((decision) => decision.batch_id)?.batch_id
            const items = decisions.filter(
              (decision) => decision.batch_id === batch && !decision.undone_by,
            )
            void (async () => {
              for (const item of items) {
                try {
                  await api.undo(ctx.jobId, item.id)
                } catch (error) {
                  setProblem(
                    `${fields.get(item.field_id) ?? item.field_id}: ${error instanceof Error ? error.message : 'Nu se poate anula.'}`,
                  )
                  break
                }
              }
              ctx.refresh('fields', 'outline', 'checks', 'log')
              invalidate('overview')
            })()
          }}
        >
          Anulează toate
        </Button>
      )}
    </div>
  )
}
