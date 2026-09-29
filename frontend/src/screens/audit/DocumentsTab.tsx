import { useState, type DragEvent } from 'react'
import { Download, Plus } from 'lucide-react'
import { api } from '../../api/endpoints.ts'
import { auditApi } from '../../api/audit.ts'
import type { AuditDocuments } from '../../api/audit-types.ts'
import { nextStage } from '../../audit/stages.ts'
import { plural } from '../../lib/plural.ts'
import { useJob } from '../../state/job.tsx'
import { useResource } from '../../state/resource.ts'
import { Button } from '../../ui/Button.tsx'
import { EmaWidget, FailureNotice } from '../../ui/Feedback.tsx'
import { SectionKey } from '../../ui/Surface.tsx'
import { AuditUploadDialog } from './AuditUploadDialog.tsx'
import { DocumentRow } from './DocumentRow.tsx'
import { RerunDialog } from './RerunDialog.tsx'

export type DocumentFilter = 'all' | 'missing' | 'verify'

/** 3b: design handoff screen component. */
export function DocumentsTab({
  documents,
  filter,
  setFilter,
}: {
  documents: AuditDocuments
  filter: DocumentFilter
  setFilter: (filter: DocumentFilter) => void
}) {
  const ctx = useJob()
  const settings = useResource('settings', api.settings)
  const [upload, setUpload] = useState<File[] | null>(null)
  const [rerun, setRerun] = useState<'intake' | 'read' | null>(null)
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const files = documents.files.filter((file) =>
    filter === 'all' ? true : filter === 'verify' ? file.status !== 'read' : file.item === null,
  )
  const needs = documents.files.filter((file) => file.status !== 'read').length
  const accepted = (ctx.fields.data ?? []).filter(
    (field) => field.review === 'accepted' || field.review === 'corrected',
  ).length
  const next = nextStage(documents)
  const run = async (stage: 'intake' | 'read' | 'visit' | 'measures') => {
    if (!ctx.job.data) return
    if (['intake', 'read'].includes(stage) && accepted > 0 && documents.runs[stage]) {
      setRerun(stage as 'intake' | 'read')
      return
    }
    setBusy(true)
    setProblem(null)
    try {
      const result = await auditApi.startStage(ctx.jobId, stage, ctx.job.data.revision)
      ctx.follow(result.run_id, stage)
      ctx.refresh('job', 'status', 'documents', 'outline')
    } catch (error) {
      setProblem(error instanceof Error ? error.message : 'Cererea nu poate fi procesată.')
    } finally {
      setBusy(false)
    }
  }
  const downloadForm = async () => {
    try {
      const blob = await auditApi.measuresForm()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'masuri-propuse.xlsx'
      link.click()
      window.setTimeout(() => {
        URL.revokeObjectURL(url)
      }, 0)
    } catch (error) {
      setProblem(error instanceof Error ? error.message : 'Cererea nu poate fi procesată.')
    }
  }
  const drop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setUpload(Array.from(event.dataTransfer.files))
  }
  return (
    <>
      <div className="audit-tab-head">
        <h2>Documente primite</h2>
        <Button
          variant="secondary"
          height={32}
          icon={Plus}
          onClick={() => {
            setUpload([])
          }}
        >
          Adaugă documente
        </Button>
      </div>
      <div className="audit-filters" role="group" aria-label="Filtre documente">
        <button
          type="button"
          aria-pressed={filter === 'all'}
          onClick={() => {
            setFilter('all')
          }}
        >
          Toate
        </button>
        <button
          type="button"
          aria-pressed={filter === 'missing'}
          onClick={() => {
            setFilter('missing')
          }}
        >
          Cu lipsuri {documents.missing.length + documents.unclassified.length}
        </button>
        <button
          type="button"
          aria-pressed={filter === 'verify'}
          onClick={() => {
            setFilter('verify')
          }}
        >
          De verificat {needs}
        </button>
      </div>
      {next && (
        <EmaWidget
          title={next.title}
          actions={
            next.action && (
              <Button
                height={32}
                loading={busy}
                disabled={busy || ctx.run?.state === 'running'}
                onClick={() => {
                  if (next.stage) void run(next.stage)
                  else if (next.filter) setFilter(next.filter)
                }}
              >
                {next.action}
              </Button>
            )
          }
        >
          {next.body}
        </EmaWidget>
      )}
      {problem && (
        <FailureNotice title="Nu am putut continua" actions={null}>
          {problem}
        </FailureNotice>
      )}
      {filter === 'all' && (
        <>
          <SectionKey>Formulare</SectionKey>
          <DocumentRow
            file={documents.anexa}
            label="Anexa 2–3"
            ocr={settings.data?.extraction.ocr === true}
          />
          <DocumentRow
            file={documents.measures}
            label="Măsuri propuse"
            ocr={settings.data?.extraction.ocr === true}
          />
          <Button variant="quiet" height={28} icon={Download} onClick={() => void downloadForm()}>
            Descarcă formularul
          </Button>
        </>
      )}
      <SectionKey>Dosarul clientului</SectionKey>
      {files.map((file) => (
        <DocumentRow
          key={file.slot}
          label={file.slot === 'cover/photo' ? 'Fotografia sediului' : undefined}
          file={file}
          ocr={settings.data?.extraction.ocr === true}
        />
      ))}
      {filter === 'missing' &&
        documents.checklist
          ?.filter((item) => !item.received)
          .map((item) => (
            <div className="audit-doc-row" key={item.number}>
              {item.number}. {item.text} · lipseşte
            </div>
          ))}
      {filter === 'all' && documents.visit && (
        <VisitGroup visit={documents.visit} current={documents.runs.visit?.current ?? false} />
      )}
      <div
        className="audit-drop"
        onDragOver={(event) => {
          event.preventDefault()
        }}
        onDrop={drop}
      >
        <Button
          variant="secondary"
          height={30}
          onClick={() => {
            setUpload([])
          }}
        >
          Trage documente aici · PDF, DOCX, XLSX, JPG
        </Button>
      </div>
      {upload && (
        <AuditUploadDialog
          dropped={upload}
          onClose={() => {
            setUpload(null)
          }}
        />
      )}
      {rerun && (
        <RerunDialog
          stage={rerun}
          count={accepted}
          onClose={() => {
            setRerun(null)
          }}
        />
      )}
    </>
  )
}

function VisitGroup({
  visit,
  current,
}: {
  visit: NonNullable<AuditDocuments['visit']>
  current: boolean
}) {
  const [open, setOpen] = useState(false)
  const count = visit.panels.reduce((sum, panel) => sum + panel.photos.length, visit.thermal.length)
  const categories = visit.panels.length + Number(visit.thermal.length > 0)
  return (
    <div className="audit-visit">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => {
          setOpen(!open)
        }}
      >
        Imagini tehnice · {plural(count, 'fişier', 'fişiere')} ·{' '}
        {plural(categories, 'categorie', 'categorii')}{' '}
        <span>{current ? 'CITIT' : 'neînregistrate'}</span>
      </button>
      {open && (
        <div>
          {visit.panels.map((panel) => (
            <p key={panel.id}>
              Contoare şi tablouri — {panel.label} · {panel.photos.length}
            </p>
          ))}
          {visit.thermal.length > 0 && <p>Imagini termografice · {visit.thermal.length}</p>}
        </div>
      )}
    </div>
  )
}
