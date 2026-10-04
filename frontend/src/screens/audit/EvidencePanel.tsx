import { useCallback, useState } from 'react'
import { ExternalLink } from 'lucide-react'
import { api } from '../../api/endpoints.ts'
import type { Evidence, Field } from '../../api/types.ts'
import { formatNumber } from '../../lib/format.ts'
import { useBlobUrl } from '../../api/blobUrl.ts'
import { useJob } from '../../state/job.tsx'
import { scalar } from '../../audit/review.ts'
import { Button } from '../../ui/Button.tsx'
import { Highlight } from '../../ui/Review.tsx'
import { Paper, SectionKey } from '../../ui/Surface.tsx'
import { ValueEditor } from '../ValueEditor.tsx'

function safeUrl(value: unknown): string | null {
  if (typeof value !== 'string') return null
  try {
    const url = new URL(value)
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null
  } catch {
    return null
  }
}

function PdfEvidence({ evidence }: { evidence: Evidence }) {
  const [problem, setProblem] = useState<string | null>(null)
  const load = useCallback(() => api.evidenceSnippet(evidence.id, true), [evidence.id])
  const onError = useCallback((error: unknown) => {
    setProblem(error instanceof Error ? error.message : 'Pagina nu s-a încărcat.')
  }, [])
  const image = useBlobUrl(load, onError)
  const locator = evidence.locator
  const open = async () => {
    try {
      const blob = await api.evidencePage(evidence.id)
      const url = URL.createObjectURL(blob)
      window.open(url, '_blank', 'noopener,noreferrer')
      window.setTimeout(() => {
        URL.revokeObjectURL(url)
      }, 60000)
    } catch (error) {
      setProblem(error instanceof Error ? error.message : 'Pagina nu s-a deschis.')
    }
  }
  return (
    <div className="audit-evidence__paper">
      <Paper className="audit-evidence__crop">
        {image ? <img src={image} alt="Fragment din document" /> : <span>Se încarcă…</span>}
      </Paper>
      <Button variant="secondary" height={28} icon={ExternalLink} onClick={() => void open()}>
        Deschide pagina
      </Button>
      <small>
        PAG. {locator && 'page' in locator && typeof locator.page === 'number' ? locator.page : ''}
      </small>
      {problem && <span role="alert">{problem}</span>}
    </div>
  )
}

/** `marked` replaces the field's own doubt when the panel opens from a 7f data warning. */
export function EvidencePanel({
  field,
  evidence,
  close,
  marked,
}: {
  field: Field
  evidence: Evidence
  close: () => void
  marked?: string
}) {
  const ctx = useJob()
  const [edit, setEdit] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const locator = evidence.locator
  const inputFields = (ctx.fields.data ?? []).filter((item) =>
    field.derivation?.inputs.includes(item.id),
  )
  const filename = evidence.file_name ?? 'Document'
  const quote = evidence.quote ?? ''
  const value = scalar(field.value)
  const text =
    quote.includes(value) && value ? (
      <>
        {quote.split(value)[0]}
        <Highlight>{value}</Highlight>
        {quote.split(value).slice(1).join(value)}
      </>
    ) : (
      quote
    )
  const reason =
    marked ??
    field.failure ??
    (field.confidence === 'partial'
      ? 'Valoarea găsită nu se potriveşte exact cu textul din document.'
      : field.confidence === 'conflict'
        ? 'Sursele dau valori diferite. Decizia intră în Jurnal şi se poate anula.'
        : 'Ema nu a găsit o potrivire exactă în document.')
  return (
    <div className="audit-evidence">
      {evidence.provenance === 'document' &&
        (locator?.kind === 'pdf_region' || locator?.kind === 'pdf_text') && (
          <PdfEvidence evidence={evidence} />
        )}
      {evidence.provenance === 'document' && locator?.kind === 'cell' && (
        <Paper className="audit-evidence__paper">
          <SectionKey>Celula din document</SectionKey>
          <strong>
            {locator.sheet}!{locator.ref}
          </strong>
          <span>{filename}</span>
        </Paper>
      )}
      {evidence.provenance === 'online' && (
        <Paper className="audit-evidence__paper">
          <SectionKey>PAGINĂ WEB · instantaneu salvat</SectionKey>
          <p>{text}</p>
          <small>
            {locator && 'url' in locator && typeof locator.url === 'string' ? locator.url : ''}
          </small>
        </Paper>
      )}
      {evidence.provenance === 'calculated' && (
        <Paper className="audit-evidence__paper">
          <strong>
            {formatNumber(value)} {field.unit}
          </strong>
          <small>
            formula {field.derivation?.formula_id} · factori {field.derivation?.factor_version}
          </small>
        </Paper>
      )}
      <div className="audit-evidence__detail">
        <SectionKey>
          {evidence.provenance === 'online'
            ? 'CITATUL DIN PAGINĂ'
            : evidence.provenance === 'calculated'
              ? 'Vezi intrările'
              : 'TEXTUL DIN DOCUMENT'}
        </SectionKey>
        {evidence.provenance === 'calculated' ? (
          inputFields.map((item) => (
            <p key={item.id}>
              {item.label} ·{' '}
              {item.value_type === 'number' ? formatNumber(scalar(item.value)) : scalar(item.value)}{' '}
              {item.unit}
            </p>
          ))
        ) : (
          <p>{text}</p>
        )}
        {evidence.highlight !== 'exact' && evidence.provenance === 'document' && (
          <small>Ema nu poate marca valoarea pe această pagină.</small>
        )}
        <SectionKey>
          {evidence.provenance === 'online'
            ? 'DE UNDE VINE'
            : marked
              ? 'DE CE E MARCAT'
              : 'DE CE E MARCAT NESIGUR'}
        </SectionKey>
        <p>
          {evidence.provenance === 'online'
            ? (evidence.trust_reason ??
              'Găsit de Ema în cercetarea online; pagina e salvată la data preluării, citatul a fost găsit exact în ea.')
            : reason}
        </p>
        {evidence.provenance === 'online' &&
          locator &&
          'url' in locator &&
          safeUrl(locator.url) && (
            <a href={safeUrl(locator.url) ?? undefined} target="_blank" rel="noopener noreferrer">
              Deschide pagina
            </a>
          )}
        {field.alternatives?.map((candidate) => (
          <Button
            key={candidate.id}
            variant="secondary"
            height={28}
            onClick={() => {
              void api.choose(ctx.jobId, field.id, candidate.id, field.revision ?? 0).then(
                () => {
                  ctx.refresh('fields', 'log', 'outline', 'checks')
                },
                (error: unknown) => {
                  setProblem(error instanceof Error ? error.message : 'Valoarea nu s-a salvat.')
                  ctx.refresh('fields')
                },
              )
            }}
          >
            Foloseşte{' '}
            {field.value_type === 'number'
              ? formatNumber(scalar(candidate.value))
              : scalar(candidate.value)}
          </Button>
        ))}
        {problem && <span role="alert">{problem}</span>}
        {edit ? (
          <ValueEditor
            field={field}
            onDone={() => {
              setEdit(false)
              close()
            }}
          />
        ) : (
          <Button
            variant="secondary"
            height={28}
            onClick={() => {
              setEdit(true)
            }}
          >
            Scrie altă valoare
          </Button>
        )}
      </div>
    </div>
  )
}
