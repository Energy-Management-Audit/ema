import { formatDate } from '../../lib/format.ts'
import { useState } from 'react'
import type { AuditOutline } from '../../api/audit-types.ts'
import { auditApi } from '../../api/audit.ts'
import { byWeek, weekRange } from '../../audit/journal.ts'
import { plural } from '../../lib/plural.ts'
import { countdown, nodeState } from '../../audit/outline.ts'
import { useJob } from '../../state/job.tsx'
import { Button } from '../../ui/Button.tsx'
import { TextField } from '../../ui/Field.tsx'
import { ProgressBar } from '../../ui/Feedback.tsx'
import { SectionKey } from '../../ui/Surface.tsx'

export function StructureActivity({ outline }: { outline: AuditOutline }) {
  const ctx = useJob()
  const [editing, setEditing] = useState(false)
  const [today] = useState(() => Date.now())
  const [date, setDate] = useState(outline.deadline.value ?? '')
  const [problem, setProblem] = useState<string | null>(null)
  const unanswered = outline.nodes.filter((node) => !node.answered && node.parent !== null)
  const weeks = byWeek(ctx.log.data ?? []).slice(0, 4)
  const visitChapters = [
    ...new Set(
      outline.nodes
        .filter((node) => node.status === 'later' && node.reason === 'visit')
        .map((node) => node.chapter),
    ),
  ]
  const futureVisit =
    outline.visit_date && new Date(outline.visit_date).getTime() > today
      ? new Date(outline.visit_date)
      : null
  const save = async (value = date) => {
    const parsed = /^\d{2}\.\d{2}\.\d{4}$/.test(value)
      ? value.split('.').reverse().join('-')
      : value
    if (parsed && !/^\d{4}-\d{2}-\d{2}$/.test(parsed)) {
      setProblem('Data nu este validă.')
      return
    }
    try {
      await auditApi.putDeadline(ctx.jobId, parsed || null, outline.deadline.revision)
      ctx.refresh('outline')
      setEditing(false)
      setProblem(null)
    } catch (error) {
      setProblem(error instanceof Error ? error.message : 'Termenul nu s-a salvat.')
      ctx.refresh('outline')
    }
  }
  return (
    <div className="audit-structure-activity">
      <SectionKey>Secţiuni fără răspuns</SectionKey>
      {unanswered.slice(0, 4).map((node) => (
        <div key={node.id} className="audit-activity-line">
          <span>
            {node.number} {node.title}
          </span>
          <small>{nodeState(node)}</small>
        </div>
      ))}
      {unanswered.length > 4 && <small>încă {unanswered.length - 4}</small>}
      <SectionKey>Pe săptămâni</SectionKey>
      {weeks.map(([week, decisions], index) => (
        <div className="audit-week" key={week}>
          <strong>
            {index === 0 ? 'Săptămâna asta' : index === 1 ? 'Săptămâna trecută' : weekRange(week)}
          </strong>
          <small>{weekRange(week)}</small>
          {(['drafted', 'done'] as const).map((state) => {
            const chapters = [
              ...new Set(
                decisions
                  .filter(
                    (decision) =>
                      decision.target_kind === 'section' && decision.after.status === state,
                  )
                  .map(
                    (decision) =>
                      outline.nodes.find((node) => node.id === decision.field_id)?.chapter,
                  )
                  .filter((chapter): chapter is number => chapter !== undefined),
              ),
            ]
            return chapters.length ? (
              <small key={state}>
                {state === 'drafted' ? 'scrise' : 'confirmate'}: cap. {chapters.join(', ')}
              </small>
            ) : null
          })}
        </div>
      ))}
      {futureVisit && visitChapters.length > 0 && (
        <div className="audit-week">
          <SectionKey>Urmează</SectionKey>
          <strong>{formatDate(futureVisit, { year: false })}</strong>
          <small>vizita în teren · deblochează cap. {visitChapters.join(', ')}</small>
        </div>
      )}
      <SectionKey>Termen client</SectionKey>
      {editing ? (
        <div className="audit-deadline">
          <TextField
            aria-label="Termen client"
            placeholder="zz.ll.aaaa"
            value={date}
            onChange={(event) => {
              setDate(event.target.value)
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter') void save()
            }}
          />
          <Button height={28} onClick={() => void save()}>
            Salvează
          </Button>
          <Button
            variant="secondary"
            height={28}
            onClick={() => {
              setDate('')
              void save('')
            }}
          >
            Şterge
          </Button>
        </div>
      ) : (
        <button
          type="button"
          className="audit-deadline-link"
          onClick={() => {
            setEditing(true)
          }}
        >
          {outline.deadline.value ? (
            <>
              {outline.deadline.value} · {countdown(outline.deadline.value)}
            </>
          ) : (
            'Stabileşte termenul'
          )}
        </button>
      )}
      {problem && (
        <p role="alert" className="audit-error">
          {problem}
        </p>
      )}
      <SectionKey>CAPITOLE SCRISE</SectionKey>
      <strong>
        {outline.written}/{outline.chapters}
      </strong>
      <ProgressBar
        value={outline.chapters ? Math.round((outline.written / outline.chapters) * 100) : 0}
      />
      <small>
        {outline.answered} din {plural(outline.total, 'secţiune', 'secţiuni')}{' '}
        {outline.total === 1 ? 'a' : 'au'} răspuns.
      </small>
    </div>
  )
}
