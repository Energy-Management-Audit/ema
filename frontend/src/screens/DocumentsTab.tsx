import { Download, File, Sheet } from 'lucide-react'
import { api } from '../api/endpoints.ts'
import type { Output } from '../api/types.ts'
import { jobHref } from '../app/route.ts'
import { formatBytes, rel } from '../lib/format.ts'
import { draftDocuments, hasIssue, isDocx, latestOf } from '../piee/readiness.ts'
import { useJob } from '../state/job.tsx'
import { jobKey, useResource } from '../state/resource.ts'
import { Button } from '../ui/Button'
import { EmaWidget } from '../ui/Feedback'
import { Icon } from '../ui/Icon'
import { Card, SectionKey } from '../ui/Surface'
import { ProblemNotice, download, useAction } from './actions.tsx'
import { PIEE_SLOTS, useReadDocuments, useSlots } from './JobHeader.tsx'
import { SlotRow, type ReadState } from './SlotRow.tsx'

export function useReadState(): ReadState {
  const { status, checks } = useJob()
  const imported = (status.data?.runs ?? []).some(
    (run) => run.stage === 'piee_import' && run.state === 'ready',
  )
  if (!imported) return 'unread'
  return hasIssue(checks.data, 'import_required') ? 'stale' : 'read'
}

function OutputRow({ output, detail }: { output: Output; detail: string }) {
  const { jobId } = useJob()
  const action = useAction()
  return (
    <div className="output-row" data-testid={`output-row-${output.id}`}>
      <Icon icon={isDocx(output) ? File : Sheet} size={16} stroke={1.6} />
      <div className="slot-row__text">
        <span className="slot-row__name slot-row__name--file">{output.name}</span>
        <span className="slot-row__detail">{detail}</span>
        <ProblemNotice problem={action.problem} />
      </div>
      <Button
        variant="secondary"
        height={28}
        icon={Download}
        loading={action.pending}
        onClick={() => {
          void action.run(() => download(jobId, output))
        }}
      >
        Descarcă
      </Button>
      <span className="slot-row__size">{formatBytes(output.size_bytes)}</span>
    </div>
  )
}

export function DocumentsTab() {
  const ctx = useJob()
  const slots = useSlots(ctx.jobId)
  const prelucrare = useResource(jobKey(ctx.jobId, 'prelucrare'), () => api.prelucrare(ctx.jobId))
  const read = useReadState()
  const reader = useReadDocuments()
  const years = prelucrare.data?.input?.years ?? []
  const fields = ctx.fields.data ?? []
  const conflicts = fields.filter((field) => field.confidence === 'conflict')
  const outputs = ctx.outputs.data ?? []
  const drafts = draftDocuments(outputs)
  const draft = drafts.at(-1)
  const workbook = latestOf(outputs, (item) => item.name.toLowerCase().endsWith('.xlsx'))
  const final = latestOf(
    outputs,
    (item) => item.kind === 'final' && item.stage === 'piee_word' && isDocx(item),
  )
  const since = (output: Output) => (output.created_at ? rel(output.created_at) : '')
  let widget = null
  if (fields.length > 0 && read !== 'read') {
    widget = (
      <EmaWidget
        title="Documentele nu sunt citite"
        actions={
          <Button
            height={32}
            loading={reader.pending || ctx.run?.state === 'running'}
            disabled={reader.pending || ctx.run?.state === 'running'}
            onClick={() => {
              void reader.start()
            }}
          >
            Citeşte documentele
          </Button>
        }
      >
        Ema citeşte fişierele şi propune datele; nimic nu intră în program până nu le verifici.
      </EmaWidget>
    )
  } else if (conflicts.length > 0) {
    widget = (
      <EmaWidget
        title={
          conflicts.length === 1
            ? '1 diferenţă aşteaptă decizia ta'
            : `${String(conflicts.length)} diferenţe aşteaptă decizia ta`
        }
        actions={
          <a
            className="ema-btn ema-btn--primary ema-btn--h32"
            href={jobHref(ctx.jobId, 'date', conflicts[0]?.id ?? null)}
          >
            Vezi diferenţa
          </a>
        }
      >
        Nu blochează ciorna; blochează exportul final.
      </EmaWidget>
    )
  }
  return (
    <div className="documents">
      <SectionKey>Intrări</SectionKey>
      <Card>
        {PIEE_SLOTS.map((slot) => (
          <SlotRow
            key={slot}
            slot={slot}
            filled={slots.data?.includes(slot) ?? false}
            read={read}
            prelucrareYears={years}
          />
        ))}
      </Card>
      {widget}
      <ProblemNotice problem={reader.problem} />
      <SectionKey>Ieşiri</SectionKey>
      <Card>
        {draft && (
          <OutputRow
            output={draft}
            detail={`ciornă ${String(drafts.length)} · generată ${since(draft)}`}
          />
        )}
        {workbook && (
          <OutputRow
            output={workbook}
            detail="generat de Ema în formatul ei · formule vii · fişier de lucru, nu e legat de document"
          />
        )}
        {final && <OutputRow output={final} detail={`final · generat ${since(final)}`} />}
        {!draft && !workbook && !final && (
          <p className="documents__none">Ciorna apare aici după prima generare.</p>
        )}
      </Card>
    </div>
  )
}
