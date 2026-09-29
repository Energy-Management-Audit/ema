import { useState } from 'react'
import { auditApi } from '../../api/audit.ts'
import type { AuditOutline } from '../../api/audit-types.ts'
import { auditHref } from '../../app/route.ts'
import { plural } from '../../lib/plural.ts'
import { navigate } from '../../app/navigate.ts'
import {
  exactBatch,
  filterFields,
  groupByChapter,
  pending,
  reviewFields,
  uncertain,
  decided,
  type ReviewFilter,
} from '../../audit/review.ts'
import { useJob } from '../../state/job.tsx'
import { invalidate } from '../../state/resource.ts'
import { Button } from '../../ui/Button.tsx'
import { EmaWidget, EmptyState, FailureNotice } from '../../ui/Feedback.tsx'
import { SectionKey } from '../../ui/Surface.tsx'
import { AuditFieldRow } from './AuditFieldRow.tsx'

/** 3c: design handoff screen component. */
export function ReviewTab({ field, outline }: { field: string | null; outline: AuditOutline }) {
  const ctx = useJob()
  const [filter, setFilter] = useState<ReviewFilter>('pending')
  const [opened, setOpened] = useState<string | null>(field)
  const [visibleCount, setVisibleCount] = useState(60)
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const all = reviewFields(ctx.fields.data ?? [])
  const waiting = all.filter(pending)
  const rejected = all.filter((item) => item.review === 'rejected')
  const accepted = all.filter((item) => item.review === 'accepted' || item.review === 'corrected')
  const unsafe = waiting.filter(uncertain)
  const exact = exactBatch(all)
  const chosen = filterFields(all, filter)
  const visible = chosen.slice(0, visibleCount)
  if (field) {
    const requested = chosen.find((item) => item.id === field)
    if (requested && !visible.some((item) => item.id === field)) visible.push(requested)
  }
  const grouped = groupByChapter(visible)
  const acceptAll = async () => {
    setBusy(true)
    setProblem(null)
    try {
      await auditApi.acceptBatch(ctx.jobId, exact)
      ctx.refresh('fields', 'log', 'outline', 'checks')
      invalidate('overview')
    } catch (error) {
      setProblem(error instanceof Error ? error.message : 'Cererea nu poate fi procesată.')
    } finally {
      setBusy(false)
    }
  }
  const photoCount = (ctx.fields.data ?? []).filter(
    (item) =>
      (item.key.startsWith('meter.') || item.key.startsWith('thermal.')) &&
      item.needs_confirmation &&
      item.review === 'pending',
  ).length
  return (
    <>
      {waiting.length ? (
        <EmaWidget
          title={
            unsafe.length
              ? `Începe cu ${plural(unsafe.length, 'câmp nesigur', 'câmpuri nesigure')}`
              : `${plural(exact.length, 'câmp rămas', 'câmpuri rămase')} ${exact.length === 1 ? 'are' : 'au'} potrivire exactă`
          }
          actions={
            <>
              {unsafe.length > 0 && (
                <Button
                  variant="secondary"
                  height={32}
                  onClick={() => {
                    setFilter('uncertain')
                    setOpened(unsafe[0]?.id ?? null)
                  }}
                >
                  Du-mă la primul
                </Button>
              )}
              {exact.length > 0 && (
                <Button
                  variant="secondary"
                  height={32}
                  disabled={busy}
                  onClick={() => void acceptAll()}
                >
                  Acceptă {plural(exact.length, 'câmp sigur', 'câmpuri sigure')}
                </Button>
              )}
            </>
          }
        >
          {exact.length > 0 &&
            (unsafe.length
              ? `Restul ${String(exact.length)} ${exact.length === 1 ? 'are' : 'au'} potrivire exactă în document — ${exact.length === 1 ? 'îl poţi accepta' : 'le poţi accepta pe toate deodată'}.`
              : 'Le poţi accepta pe toate deodată.')}
        </EmaWidget>
      ) : (
        <EmptyState
          mark="done"
          title={
            rejected.length
              ? 'Nu mai e nimic de confirmat.'
              : accepted.length === 1
                ? 'Câmpul este acceptat'
                : `Toate cele ${plural(accepted.length, 'câmp', 'câmpuri')} sunt acceptate`
          }
          actions={
            <>
              <Button
                height={32}
                onClick={() => {
                  navigate(auditHref(ctx.jobId, 'structura'))
                }}
              >
                Treci la structură
              </Button>
              <Button
                variant="secondary"
                height={32}
                onClick={() => {
                  setFilter('accepted')
                }}
              >
                Vezi {plural(all.filter(decided).length, 'câmp acceptat', 'câmpuri acceptate')}
              </Button>
            </>
          }
        >
          {rejected.length
            ? 'Următorul pas e structura raportului.'
            : 'Nu mai e nimic de confirmat. Următorul pas e structura raportului.'}
        </EmptyState>
      )}
      {problem && (
        <FailureNotice title="Nu am putut accepta câmpurile" actions={null}>
          {problem}
        </FailureNotice>
      )}
      {photoCount > 0 && (
        <Button
          variant="quiet"
          height={30}
          onClick={() => {
            navigate(auditHref(ctx.jobId, 'masuratori'))
          }}
        >
          {plural(photoCount, 'valoare citită', 'valori citite')} de pe fotografii aşteaptă
          confirmarea
        </Button>
      )}
      <div className="audit-filters" role="group" aria-label="Filtre revizuire">
        <button
          type="button"
          aria-pressed={filter === 'pending'}
          onClick={() => {
            setFilter('pending')
          }}
        >
          În aşteptare {waiting.length}
        </button>
        <button
          type="button"
          aria-pressed={filter === 'uncertain'}
          onClick={() => {
            setFilter('uncertain')
          }}
        >
          Nesigure {unsafe.length}
        </button>
        <button
          type="button"
          aria-pressed={filter === 'accepted'}
          onClick={() => {
            setFilter('accepted')
          }}
        >
          Acceptate {all.filter(decided).length}
        </button>
      </div>
      {grouped.map(([chapter, fields]) => (
        <section className="audit-review-group" key={chapter}>
          <SectionKey>
            {chapter
              ? `CAP. ${chapter.slice(2)} · ${(outline.nodes.find((node) => node.id === chapter)?.title ?? '').toLocaleUpperCase('ro-RO')}`
              : 'ALTE DATE'}
          </SectionKey>
          {fields.map((item) => (
            <AuditFieldRow
              key={item.id}
              field={item}
              open={opened === item.id}
              onOpen={() => {
                setOpened(opened === item.id ? null : item.id)
              }}
            />
          ))}
        </section>
      ))}
      {chosen.length > visible.length && (
        <Button
          variant="secondary"
          height={32}
          onClick={() => {
            setVisibleCount(visibleCount + 60)
          }}
        >
          Arată încă {plural(Math.min(60, chosen.length - visible.length), 'câmp', 'câmpuri')}
        </Button>
      )}
    </>
  )
}
