import { useState } from 'react'
import type { AuditOutline, OutlineNode } from '../../api/audit-types.ts'
import { auditApi } from '../../api/audit.ts'
import { plural } from '../../audit/plural.ts'
import { aggregate, displayTitle, holding, nodeState } from '../../audit/outline.ts'
import { useJob } from '../../state/job.tsx'
import { Button } from '../../ui/Button.tsx'
import { Status } from '../../ui/Chip.tsx'
import { EmaWidget } from '../../ui/Feedback.tsx'
import { ProgressBar } from '../../ui/Feedback.tsx'
import { SectionKey } from '../../ui/Surface.tsx'
import { SectionActions } from './SectionActions.tsx'

export function StructureTab({ outline }: { outline: AuditOutline }) {
  const [expanded, setExpanded] = useState<string | null>('ch3')
  const roots = outline.nodes.filter((node) => node.parent === null)
  return (
    <>
      <div className="audit-tab-head">
        <h2>Structura raportului</h2>
        <span>Vizita în teren: {outline.visit_date ?? 'nestabilită'} · Şablon: EMA 2026</span>
      </div>
      <div className="audit-structure">
        {roots.map((root) => {
          const leaves = outline.nodes.filter(
            (node) => node.chapter === root.chapter && node.id !== root.id,
          )
          const state = aggregate(leaves)
          const first = leaves.find((node) => holding(node))
          return (
            <div
              key={root.id}
              className="audit-chapter"
              data-open={expanded === root.id || undefined}
            >
              <div className="audit-chapter__row">
                <div>
                  <strong>
                    {root.number}. {displayTitle(root.title)}
                  </strong>
                  <Status tone={state === 'gata' ? 'ok' : 'warn'}>{state}</Status>
                </div>
                <p>{first ? holding(first) : ''}</p>
                <Button
                  variant="secondary"
                  height={30}
                  onClick={() => {
                    setExpanded(expanded === root.id ? null : root.id)
                  }}
                >
                  {expanded === root.id ? 'Închide' : 'Deschide'}
                </Button>
              </div>
              {expanded === root.id && <ChapterOpen root={root} nodes={outline.nodes} />}
            </div>
          )
        })}
      </div>
      <EmaWidget title="Exportul final" actions={null}>
        Exportul final cere un răspuns la fiecare secţiune: gata, „nu se aplică” confirmat de tine
        sau completată. Ema nu marchează singură o secţiune ca „nu se aplică”.
      </EmaWidget>
      <div className="audit-structure-footer">
        <SectionKey>CAPITOLE SCRISE</SectionKey>
        <strong>
          {outline.written}/{outline.chapters}
        </strong>
        <ProgressBar
          value={outline.chapters ? Math.round((outline.written / outline.chapters) * 100) : 0}
        />
        <span>
          {outline.answered} din {plural(outline.total, 'secţiune', 'secţiuni')}{' '}
          {outline.total === 1 ? 'a' : 'au'} răspuns.
        </span>
      </div>
    </>
  )
}

function ChapterOpen({ root, nodes }: { root: OutlineNode; nodes: OutlineNode[] }) {
  const ctx = useJob()
  const [note, setNote] = useState(root.note?.text ?? '')
  const [allBlockers, setAllBlockers] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const rows = nodes.filter((node) => node.chapter === root.chapter && node.id !== root.id)
  const blockers = rows.filter((node) => holding(node))
  const save = async () => {
    if (note === (root.note?.text ?? '')) return
    try {
      await auditApi.putNote(ctx.jobId, root.id, note, root.note?.revision ?? 0)
      ctx.refresh('outline')
    } catch (error) {
      setProblem(error instanceof Error ? error.message : 'Cererea nu poate fi procesată.')
      ctx.refresh('outline')
    }
  }
  return (
    <div className="audit-chapter__open">
      <div className="audit-chapter__detail">
        <div>
          <SectionKey>SUBCAPITOLE</SectionKey>
          {rows.map((node) => (
            <div className="audit-section-row" key={node.id}>
              <div className="audit-section-row__main">
                <Status
                  tone={node.status === 'done' ? 'ok' : 'warn'}
                  mark={node.status === 'later' ? 'later' : node.status === 'n/a' ? 'na' : 'dot'}
                >
                  <span className="audit-section-row__name">
                    {node.number} {displayTitle(node.title)}
                  </span>
                </Status>
                <span className="audit-section-row__state">{nodeState(node)}</span>
              </div>
              <SectionActions node={node} />
            </div>
          ))}
        </div>
        <div>
          <SectionKey>CE ŢINE CAPITOLUL PE LOC</SectionKey>
          {(allBlockers ? blockers : blockers.slice(0, 3)).map(
            (node) =>
              holding(node) && (
                <p key={node.id} className="audit-holding">
                  {holding(node)}
                </p>
              ),
          )}
          {blockers.length > 3 && (
            <Button
              variant="quiet"
              height={26}
              onClick={() => {
                setAllBlockers(!allBlockers)
              }}
            >
              {allBlockers ? 'Arată mai puţine' : `Arată toate (${String(blockers.length)})`}
            </Button>
          )}
          <SectionKey>NOTIŢA TA</SectionKey>
          <textarea
            className="ema-field audit-note"
            aria-label="Notiţa ta"
            value={note}
            onChange={(event) => {
              setNote(event.target.value)
            }}
            onBlur={() => void save()}
          />
          {problem && (
            <p className="audit-error" role="alert">
              {problem}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
