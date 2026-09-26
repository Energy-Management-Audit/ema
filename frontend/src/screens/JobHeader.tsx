import { useRef, useState } from 'react'
import { Plus } from 'lucide-react'
import { api } from '../api/endpoints.ts'
import { jobHref, type Tab } from '../app/route.ts'
import { navigate } from '../app/navigate.ts'
import { rel } from '../lib/format.ts'
import { draftDocuments, hasIssue, previewPdf } from '../piee/readiness.ts'
import { useJob } from '../state/job.tsx'
import { jobKey, useResource } from '../state/resource.ts'
import { Button } from '../ui/Button'
import { ProblemNotice, STALE_CODES, openPreview, useAction } from './actions.tsx'
import { RegenerateDialog } from './RegenerateDialog.tsx'
import { UploadDialog } from './UploadDialog.tsx'

export const PIEE_SLOTS = ['anexa', 'prelucrare', 'questionnaire', 'previous_piee'] as const

export function useSlots(jobId: string) {
  return useResource(jobKey(jobId, 'slots'), () => api.slots(jobId))
}

export function useSlotCount(jobId: string): number | null {
  const slots = useSlots(jobId)
  if (!slots.data) return null
  return slots.data.filter((slot) => (PIEE_SLOTS as readonly string[]).includes(slot)).length
}

/** Starting a draft, shared by the header and the run panel's retry. */
export function useGenerate() {
  const ctx = useJob()
  const action = useAction()
  const start = () =>
    action.run(
      async () => {
        const started = await api.generate(ctx.jobId, ctx.job.data?.revision ?? 0)
        ctx.follow(started.run_id, started.stage)
        ctx.refresh('job', 'status')
      },
      (problem) => {
        if (STALE_CODES.has(problem.code)) ctx.refresh('job', 'checks', 'status')
      },
    )
  return { ...action, start }
}

function DraftStatus() {
  const { outputs, checks } = useJob()
  const drafts = draftDocuments(outputs.data ?? [])
  const latest = drafts.at(-1)
  if (hasIssue(checks.data, 'stale')) {
    return <span className="job-draft job-draft--stale">ciornă veche · datele s-au schimbat</span>
  }
  if (!latest) return <span className="job-draft">nicio ciornă</span>
  const when = latest.created_at ? ` · generată ${rel(latest.created_at)}` : ''
  return <span className="job-draft">{`ciornă ${String(drafts.length)}${when}`}</span>
}

export function JobActions({ tab }: { tab: Tab }) {
  const ctx = useJob()
  const generate = useGenerate()
  const preview = useAction()
  const [dialog, setDialog] = useState<'regenerate' | null>(null)
  const [upload, setUpload] = useState<File | null>(null)
  const picker = useRef<HTMLInputElement>(null)
  const outputs = ctx.outputs.data ?? []
  const pdf = previewPdf(outputs)
  const latestDraft = draftDocuments(outputs).at(-1)
  const running = ctx.run?.state === 'running' || ctx.job.data?.state === 'running'
  const unread = hasIssue(ctx.checks.data, 'import_required') || ctx.fields.data?.length === 0
  let primary
  if (tab === 'documente') {
    primary = (
      <Button
        variant="secondary"
        height={34}
        icon={Plus}
        onClick={() => {
          picker.current?.click()
        }}
      >
        Adaugă documente
      </Button>
    )
  } else if (tab === 'date') {
    primary = (
      <Button
        variant="olive"
        height={34}
        loading={running || generate.pending}
        disabled={running || generate.pending || unread}
        title={unread ? 'Citeşte întâi documentele.' : undefined}
        onClick={() => {
          if (latestDraft?.edited_externally) setDialog('regenerate')
          else void generate.start()
        }}
      >
        Generează programul
      </Button>
    )
  } else {
    primary = (
      <Button
        variant="olive"
        height={34}
        onClick={() => {
          navigate(jobHref(ctx.jobId, 'predare'))
        }}
      >
        Exportă PIEE
      </Button>
    )
  }
  return (
    <>
      <DraftStatus />
      <Button
        variant="secondary"
        height={34}
        disabled={!pdf || preview.pending}
        title={pdf ? undefined : 'Previzualizarea apare după generarea pachetului.'}
        onClick={() => {
          if (pdf) void preview.run(() => openPreview(ctx.jobId, pdf))
        }}
      >
        Previzualizare
      </Button>
      {primary}
      {(generate.problem ?? preview.problem) && (
        <div className="job-header-problem">
          <ProblemNotice problem={generate.problem ?? preview.problem} />
        </div>
      )}
      {dialog === 'regenerate' && latestDraft && (
        <RegenerateDialog
          name={latestDraft.name}
          onClose={() => {
            setDialog(null)
          }}
          onConfirm={() => {
            setDialog(null)
            void generate.start()
          }}
        />
      )}
      <input
        ref={picker}
        type="file"
        accept=".xls,.xlsx,.docx,.doc"
        className="ema-visually-hidden"
        data-testid="upload-input"
        tabIndex={-1}
        onChange={(event) => {
          setUpload(event.target.files?.[0] ?? null)
          event.target.value = ''
        }}
      />
      {upload && (
        <UploadDialog
          file={upload}
          onClose={() => {
            setUpload(null)
          }}
        />
      )}
    </>
  )
}

/** Reading the documents (the import stage), from S2, S3 and the run panel's retry. */
export function useReadDocuments() {
  const ctx = useJob()
  const action = useAction()
  const start = () =>
    action.run(
      async () => {
        const started = await api.readDocuments(ctx.jobId, ctx.job.data?.revision ?? 0)
        ctx.follow(started.run_id, started.stage)
        ctx.refresh('job', 'status')
      },
      (problem) => {
        if (STALE_CODES.has(problem.code)) ctx.refresh('job', 'checks', 'status')
      },
    )
  return { ...action, start }
}

/** The final package (piee_word), from 7a and the run panel's retry. */
export function useGeneratePackage() {
  const ctx = useJob()
  const action = useAction()
  const start = () =>
    action.run(
      async () => {
        const started = await api.generatePackage(ctx.jobId, ctx.job.data?.revision ?? 0)
        ctx.follow(started.run_id, started.stage)
        ctx.refresh('job', 'status')
      },
      (problem) => {
        if (STALE_CODES.has(problem.code)) ctx.refresh('job', 'checks', 'status', 'outputs')
      },
    )
  return { ...action, start }
}
