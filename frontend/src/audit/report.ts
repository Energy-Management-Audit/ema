import { plural as countRo } from '../lib/plural.ts'
// What the Raport Word (3d) and Predare (7a) screens show, derived from the report view, the run
// and the readiness the API computes. Nothing here is re-computed from documents.

import type {
  AuditReport,
  AuditSection,
  RenderMarker,
  RenderSummary,
  RenderUnitPlan,
} from '../api/audit-report-types.ts'
import type { ExportChecks } from '../api/types.ts'

export type TocState = 'done' | 'working' | 'todo'
export type TocItem = { number: number; title: string; page: number | null; state: TocState }

/** Her master structure (PLAN §3.2): the chapters shown before any render. */
export const CHAPTERS: ReadonlyArray<{ number: number; title: string }> = [
  { number: 1, title: 'Descrierea şi scopul auditului' },
  { number: 2, title: 'Descrierea şi istoricul societăţii' },
  { number: 3, title: 'Descrierea situaţiei existente' },
  { number: 4, title: 'Analiza consumurilor energetice' },
  { number: 5, title: 'Bilanţurile energetice' },
  { number: 6, title: 'Măsuri de creştere a eficienţei energetice' },
  { number: 7, title: 'Surse de finanţare' },
]

export type Progress = { running: boolean; done: number; total: number }

/** The newest draft's summary, if that draft finished. */
export function draftSummary(report: AuditReport | undefined): RenderSummary | null {
  return report?.draft?.state === 'ready' ? report.draft.summary : null
}

/** CUPRINS: the rendered chapters (or her seven), each done, being written, or still to do. */
export function tocItems(summary: RenderSummary | null, progress: Progress): TocItem[] {
  const chapters = summary
    ? summary.chapters.map((item) => ({ number: item.number, title: item.title, page: item.page }))
    : CHAPTERS.map((item) => ({ ...item, page: null }))
  return chapters.map((item, index) => ({
    ...item,
    state: progress.running
      ? index < progress.done
        ? 'done'
        : index === progress.done
          ? 'working'
          : 'todo'
      : summary
        ? 'done'
        : 'todo',
  }))
}

/** The markers' sections, each named once, in document order. */
export function markerLabels(markers: RenderMarker[]): string[] {
  return [...new Set(markers.map((item) => item.label))]
}

export function unitLine(plan: RenderUnitPlan): string {
  const line = [
    countRo(plan.processes, 'secţie', 'secţii'),
    countRo(plan.measured_panels, 'tablou măsurat', 'tablouri măsurate'),
    countRo(plan.measures, 'măsură', 'măsuri'),
  ].join(' · ')
  return plan.processes_source === 'default' ? `${line} · număr de secţii presupus` : line
}

/** Whether every confirmed field has a document source, else what is still open or typed in. */
export function fieldsLine(summary: RenderSummary): string {
  const open = summary.fields_total - summary.fields_confirmed
  if (open > 0) return `${countRo(open, 'câmp', 'câmpuri')} încă în revizuire`
  if (summary.fields_manual > 0)
    return countRo(summary.fields_manual, 'câmp introdus manual', 'câmpuri introduse manual')
  return 'toate au sursă în documente'
}

/** The page of the preview a TOC entry scrolls to: the TOC's own page number when Word set it. */
export function pageIndex(page: number | null, pages: number): number | null {
  if (page === null || pages === 0) return null
  return Math.min(Math.max(page, 1), pages) - 1
}

export type AuditCheck = { label: string; tone: 'ok' | 'err'; detail: string }

const CHECKS: ReadonlyArray<{ label: string; codes: string[]; photos?: true }> = [
  { label: 'Toate secţiunile au răspuns', codes: ['section_open', 'na_recheck', 'chapter_empty'] },
  { label: 'Nicio ciornă nu e veche', codes: ['stale', 'final_stale', 'cover_photo_changed'] },
  { label: 'Toate diferenţele dintre surse sunt decise', codes: ['conflict'] },
  {
    label: 'Valorile citite de pe fotografii sunt confirmate',
    codes: ['reading_unconfirmed'],
    photos: true,
  },
  { label: 'Toate textele sunt scrise', codes: ['narrative_missing', 'ai_wording'] },
]

/** 7a for an audit: the five checks from the readiness' blocking codes. The first one counts the
 * sections that answered (done or n/a); the photo check is hidden when the job has no photos. */
export function auditChecks(
  checks: ExportChecks | undefined,
  sections: AuditSection[] | undefined,
  hasPhotos: boolean,
): AuditCheck[] {
  const blocking = checks?.readiness.blocking ?? []
  return CHECKS.filter((check) => hasPhotos || !check.photos).map((check, index) => {
    const count = blocking.filter((issue) => check.codes.includes(issue.code)).length
    let detail = count > 0 ? String(count) : 'la zi'
    if (index === 0 && sections) {
      const answered = sections.filter((item) => ['done', 'n/a'].includes(item.status)).length
      detail = `${String(answered)}/${String(sections.length)}`
    }
    return { label: check.label, tone: count > 0 ? 'err' : 'ok', detail }
  })
}

/** Problems that mean the page is out of date: the screen refetches and says so. */
export const EXPORT_STALE = new Set(['hash_mismatch', 'output_stale', 'not_ready', 'job_running'])

/** A stale final is what a new final replaces: it alone never blocks generating one. */
export function canGenerateFinal(checks: ExportChecks | undefined): boolean {
  return (checks?.readiness.blocking ?? []).every((issue) => issue.code === 'final_stale')
}
