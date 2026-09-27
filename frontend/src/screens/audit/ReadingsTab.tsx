import { api } from '../../api/endpoints.ts'
import { photoForField, readingGroups } from '../../audit/readings.ts'
import { useJob } from '../../state/job.tsx'
import { jobKey, useResource } from '../../state/resource.ts'
import { Button } from '../../ui/Button.tsx'
import { FailureNotice } from '../../ui/Feedback.tsx'
import { SectionKey } from '../../ui/Surface.tsx'
import { ReadingRow } from '../ReadingRow.tsx'

export function ReadingsTab({ field }: { field: string | null }) {
  const ctx = useJob()
  const [starting, setStarting] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const visit = useResource(jobKey(ctx.jobId, 'visit'), () => api.visit(ctx.jobId))
  const groups = visit.data && ctx.fields.data ? readingGroups(ctx.fields.data, visit.data) : []
  const refresh = () => {
    ctx.refresh('fields', 'visit', 'log', 'checks', 'outline')
  }
  const start = async () => {
    if (!ctx.job.data || starting) return
    setStarting(true)
    setProblem(null)
    try {
      const result = await api.startReadings(ctx.jobId, ctx.job.data.revision)
      ctx.follow(result.run_id, 'readings')
      refresh()
    } catch (error) {
      setProblem(error instanceof Error ? error.message : 'Cererea nu poate fi procesată.')
    } finally {
      setStarting(false)
    }
  }
  return (
    <div className="readings-screen">
      <div className="audit-tab-head">
        <h2>Măsurători</h2>
        <Button
          height={32}
          loading={starting}
          disabled={starting || !ctx.job.data}
          onClick={() => void start()}
        >
          Citeşte fotografiile
        </Button>
      </div>
      {problem && (
        <FailureNotice title={problem} actions={null}>
          {problem}
        </FailureNotice>
      )}
      {Boolean(visit.error) && (
        <FailureNotice
          title="Nu am putut încărca măsurătorile"
          actions={
            <Button variant="secondary" height={30} onClick={refresh}>
              Încearcă din nou
            </Button>
          }
        >
          {visit.error instanceof Error ? visit.error.message : 'Cererea nu poate fi procesată.'}
        </FailureNotice>
      )}
      {!visit.data && !visit.error && <p>Se încarcă…</p>}
      {visit.data && groups.length === 0 && <p>Nu sunt fotografii de măsurători.</p>}
      {groups.map((group) => (
        <section className="readings-group" key={group.id}>
          <SectionKey>{group.label}</SectionKey>
          {group.fields.length === 0 && <p>Nu sunt valori citite.</p>}
          {group.fields.map((item) => (
            <ReadingRow
              key={item.id}
              jobId={ctx.jobId}
              field={item}
              photo={visit.data ? photoForField(item, visit.data) : null}
              decisions={ctx.log.data ?? []}
              focus={field === item.id}
              refresh={refresh}
            />
          ))}
        </section>
      ))}
    </div>
  )
}
import { useState } from 'react'
