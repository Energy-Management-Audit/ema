import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Decision, Field, VisitPhoto } from '../api/types.ts'
import { api } from '../api/endpoints.ts'
import { useBlobUrl } from '../api/blobUrl.ts'
import { ApiProblem } from '../api/client.ts'
import { parseNumber, withUnit } from '../lib/format.ts'
import { readingLabel } from '../audit/readings.ts'
import { Button } from '../ui/Button'
import { FailureNotice } from '../ui/Feedback.tsx'
import { Status } from '../ui/Chip'
import { TextField } from '../ui/Field'
import { FieldReviewRow, ReviewValue, SourceButton } from '../ui/Review'
import { Paper, SectionKey } from '../ui/Surface'
import { ProblemNotice, useAction } from './actions.tsx'

type Props = {
  jobId: string
  field: Field
  photo: VisitPhoto | null
  decisions: Decision[]
  focus: boolean
  refresh: () => void
}

export function ReadingRow({ jobId, field, photo, decisions, focus, refresh }: Props) {
  const [open, setOpen] = useState(focus)
  const [writing, setWriting] = useState(false)
  const [text, setText] = useState('')
  const [invalid, setInvalid] = useState<string | null>(null)
  const [imageError, setImageError] = useState<string | null>(null)
  const evidenceId = open && photo ? field.evidence?.[0] : undefined
  const snippetLoad = useMemo(
    () => (evidenceId ? () => api.evidenceSnippet(evidenceId, true) : null),
    [evidenceId],
  )
  const pageLoad = useMemo(
    () => (evidenceId ? () => api.evidencePage(evidenceId) : null),
    [evidenceId],
  )
  const reportImageError = useCallback((error: unknown) => {
    setImageError(error instanceof ApiProblem ? error.title : 'Cererea nu poate fi procesată.')
  }, [])
  const snippetUrl = useBlobUrl(snippetLoad, reportImageError)
  const pageUrl = useBlobUrl(pageLoad, reportImageError)
  const row = useRef<HTMLDivElement>(null)
  const action = useAction()
  useEffect(() => {
    if (focus) row.current?.scrollIntoView({ block: 'center' })
  }, [focus])
  const pending = field.needs_confirmation === true
  const missing = field.value === null || field.value === undefined || field.review === 'rejected'
  const last = decisions
    .filter((item) => item.field_id === field.id && !item.undone_by && item.action !== 'undo')
    .at(-1)
  const shown = missing
    ? '[de completat]'
    : field.value_type === 'number'
      ? withUnit(String(field.value), field.unit)
      : String(field.value)
  const accept = () => {
    void action.run(async () => {
      await api.accept(jobId, field.id, field.revision ?? 1)
      refresh()
    }, refresh)
  }
  const correct = () => {
    const parsed =
      field.value_type === 'number'
        ? parseNumber(text)
        : text.trim()
          ? { value: text.trim() }
          : { error: 'Valoarea lipseşte.' }
    if ('error' in parsed) {
      setInvalid(parsed.error)
      return
    }
    setInvalid(null)
    void action.run(async () => {
      await api.correct(jobId, field.id, parsed.value, field.revision ?? 1)
      setWriting(false)
      refresh()
    }, refresh)
  }
  const undo = () => {
    if (!last) return
    void action.run(async () => {
      await api.undo(jobId, last.id)
      refresh()
    }, refresh)
  }
  const editor = (
    <form
      className="reading-editor"
      onSubmit={(event) => {
        event.preventDefault()
        correct()
      }}
    >
      <TextField
        aria-label={readingLabel(field)}
        value={text}
        onChange={(event) => {
          setText(event.target.value)
        }}
      />
      {field.unit && <span>{field.unit}</span>}
      <Button type="submit" height={30} loading={action.pending}>
        Salvează
      </Button>
      <Button
        variant="secondary"
        height={30}
        onClick={() => {
          setWriting(false)
        }}
      >
        Renunţă
      </Button>
      {invalid && <span role="alert">{invalid}</span>}
    </form>
  )
  return (
    <div ref={row} data-testid={`reading-row-${field.id}`}>
      <FieldReviewRow
        label={readingLabel(field)}
        status={
          pending ? (
            <Status tone="warn">de verificat</Status>
          ) : missing ? (
            <Status tone="err">lipseşte</Status>
          ) : (
            <Status tone="ok" mark="accepted">
              {field.review === 'corrected' ? 'scris de tine' : 'acceptat'}
            </Status>
          )
        }
        value={<ReviewValue>{shown}</ReviewValue>}
        source={
          photo && field.evidence?.[0] ? (
            <SourceButton
              open={open}
              onClick={() => {
                setOpen(!open)
              }}
            >
              {photo.name}
            </SourceButton>
          ) : undefined
        }
        actions={
          missing ? (
            <Button
              variant="secondary"
              height={28}
              onClick={() => {
                setWriting(!writing)
              }}
            >
              Scrie valoarea
            </Button>
          ) : pending ? (
            <Button height={28} loading={action.pending} onClick={accept}>
              Acceptă
            </Button>
          ) : last ? (
            <Button variant="secondary" height={28} loading={action.pending} onClick={undo}>
              Anulează
            </Button>
          ) : undefined
        }
        snippet={
          open && photo && field.evidence?.[0] ? (
            <div className="reading-snippet">
              {imageError && (
                <FailureNotice title="Nu am putut încărca fotografia" actions={null}>
                  {imageError}
                </FailureNotice>
              )}
              <Paper>
                {snippetUrl && <img src={snippetUrl} alt={`Fotografie: ${photo.name}`} />}
              </Paper>
              <div className="reading-snippet__side">
                <SectionKey>DE CE E MARCAT NESIGUR</SectionKey>
                <p>Valoare citită de pe fotografie; verifică cifrele pe imagine.</p>
                {pageUrl && (
                  <a href={pageUrl} target="_blank" rel="noreferrer">
                    Deschide pagina
                  </a>
                )}
                {pending && (
                  <div className="reading-snippet__actions">
                    <Button height={30} loading={action.pending} onClick={accept}>
                      Acceptă
                    </Button>
                    <Button
                      variant="secondary"
                      height={30}
                      onClick={() => {
                        setWriting(true)
                      }}
                    >
                      Scrie altă valoare
                    </Button>
                  </div>
                )}
                {writing && editor}
              </div>
            </div>
          ) : undefined
        }
      />
      {writing && (!open || !photo) && editor}
      <ProblemNotice problem={action.problem} />
      {field.presence === 'failed' && <span role="alert">{field.failure}</span>}
    </div>
  )
}
