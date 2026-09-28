import { useState } from 'react'
import { auditApi } from '../../api/audit.ts'
import type { OutlineNode } from '../../api/audit-types.ts'
import { ApiProblem } from '../../api/client.ts'
import { displayTitle } from '../../audit/outline.ts'
import { useJob } from '../../state/job.tsx'
import { invalidate } from '../../state/resource.ts'
import { Button } from '../../ui/Button.tsx'

/** The human confirmation in the 3j open chapter card. */
export function ChapterConfirm({ root, nodes }: { root: OutlineNode; nodes: OutlineNode[] }) {
  const ctx = useJob()
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const drafted = nodes.filter((node) => node.chapter === root.chapter && node.status === 'drafted')

  const confirm = async () => {
    setBusy(true)
    setProblem(null)
    try {
      await auditApi.patchSections(ctx.jobId, drafted)
      ctx.refresh('outline', 'checks', 'log')
      invalidate('overview')
    } catch (error) {
      if (error instanceof ApiProblem && error.code === 'sections_stale') {
        try {
          const updated = await auditApi.outline(ctx.jobId)
          const titles = updated.nodes
            .filter(
              (node) => node.chapter === root.chapter && node.status === 'drafted' && node.stale,
            )
            .map((node) => displayTitle(node.title))
          setProblem(`Ciorna e veche la: ${titles.join(', ')}.`)
        } catch (refreshError) {
          setProblem(
            refreshError instanceof Error ? refreshError.message : 'Cererea nu poate fi procesată.',
          )
        }
        ctx.refresh('outline')
      } else if (error instanceof ApiProblem && error.code === 'stale_revision') {
        ctx.refresh('outline')
        setProblem('Secţiunea s-a modificat între timp.')
      } else {
        setProblem(error instanceof Error ? error.message : 'Cererea nu poate fi procesată.')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="audit-chapter__confirm">
      <Button
        variant="secondary"
        height={30}
        disabled={busy || drafted.length === 0}
        loading={busy}
        onClick={() => void confirm()}
      >
        Marchează ca pregătit
      </Button>
      {problem && (
        <p className="audit-error" role="alert">
          {problem}
        </p>
      )}
    </div>
  )
}
