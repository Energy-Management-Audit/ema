// What blocks the final export, the four checks of 7a, and the header's draft/preview state.
// All of it is read from the readiness the API computes; nothing is re-derived here.

import type { ExportChecks, Field, Issue, Output, PieeSummary } from '../api/types.ts'
import { plural } from '../lib/plural.ts'
import { formatNumber } from '../lib/format.ts'
import { fieldLabel } from './labels.ts'

export type Tone = 'ok' | 'warn' | 'err'
export type BlockItem = {
  tone: Tone
  status: string
  label: string
  detail?: string
  fieldId?: string
}

export function blockingIssues(checks: ExportChecks | undefined): Issue[] {
  return checks?.readiness.blocking ?? []
}

export function hasIssue(checks: ExportChecks | undefined, code: string): boolean {
  return blockingIssues(checks).some((issue) => issue.code === code)
}

function label(issue: Issue, byId: Map<string, Field>, year: number | null): string {
  const field = issue.field_id ? byId.get(issue.field_id) : undefined
  return field ? fieldLabel(field.key, field.label, year) : issue.message
}

export function blockingItems(
  checks: ExportChecks | undefined,
  fields: Field[],
  missing: Field[],
  year: number | null,
): BlockItem[] {
  const byId = new Map(fields.map((field) => [field.id, field]))
  const blocking = blockingIssues(checks)
  const items: BlockItem[] = blocking.map((issue): BlockItem => {
    const fieldId = issue.field_id ?? undefined
    switch (issue.code) {
      case 'conflict':
        return {
          tone: 'err',
          status: 'conflict',
          label: label(issue, byId, year),
          detail: 'se decide o dată; decizia intră în Jurnal',
          fieldId,
        }
      case 'missing':
        return {
          tone: 'warn',
          status: 'lipseşte',
          label: label(issue, byId, year),
          detail: 'apare roşu „n.d.” în ciornă',
          fieldId,
        }
      case 'stale':
        return { tone: 'warn', status: 'ciornă veche', label: 'generează din nou programul' }
      case 'months_annual_mismatch':
        return {
          tone: 'err',
          status: 'de corectat',
          label: label(issue, byId, year),
          detail: 'suma lunilor diferă de totalul anual',
          fieldId,
        }
      case 'import_required':
        return { tone: 'warn', status: 'necitite', label: 'citeşte din nou documentele' }
      default:
        return { tone: 'err', status: 'de rezolvat', label: issue.message }
    }
  })
  const listed = new Set(blocking.map((issue) => issue.field_id))
  for (const field of missing) {
    if (listed.has(field.id)) continue
    items.push({
      tone: 'warn',
      status: 'lipseşte',
      label: fieldLabel(field.key, field.label, year),
      detail: 'apare roşu „n.d.” în ciornă',
      fieldId: field.id,
    })
  }
  return items
}

export function blockingFooter(checks: ExportChecks | undefined): string {
  const count = blockingIssues(checks).length
  if (count === 0) return 'Nimic nu blochează exportul final.'
  return `Exportul final se poate face după ${plural(count, 'decizie', 'decizii')}.`
}

const DOCUMENT_CODES = new Set([
  'stale',
  'draft_missing',
  'import_required',
  'untouched_anchor',
  'package',
])

export type ExportCheckView = { tone: Tone; label: string; detail: string }

export function exportChecks(
  checks: ExportChecks | undefined,
  summary: PieeSummary | undefined,
): ExportCheckView[] {
  const blocking = blockingIssues(checks)
  const total = summary?.measures_total ?? 0
  const complete = summary?.measures_complete ?? 0
  const annualIds = new Set(summary?.total_tep.field_ids ?? [])
  const onAnnual = blocking.filter(
    (issue) =>
      issue.code === 'months_annual_mismatch' || (issue.field_id && annualIds.has(issue.field_id)),
  )
  const open = blocking.filter(
    (issue) =>
      (issue.code === 'conflict' || issue.code === 'missing') &&
      !(issue.field_id && annualIds.has(issue.field_id)),
  )
  const documentIssue = blocking.find((issue) => DOCUMENT_CODES.has(issue.code))
  const totalTep = summary?.total_tep.value
  return [
    {
      tone: complete === total ? 'ok' : 'warn',
      label:
        total === 1
          ? 'Măsura are termen, investiţie, economie şi recuperare'
          : `Toate cele ${plural(total, 'măsură', 'măsuri')} au termen, investiţie, economie şi recuperare`,
      detail: `${String(complete)} / ${String(total)}`,
    },
    {
      tone: onAnnual.length > 0 ? 'err' : 'ok',
      label: 'Totalul anual coincide cu „Date anuale” din Anexa 2–3',
      detail: totalTep ? `${formatNumber(totalTep, 'tep', true)} tep` : '—',
    },
    {
      tone: open.length > 0 ? 'err' : 'ok',
      label: 'Toate diferenţele dintre surse sunt decise',
      detail: `${String(open.length)} deschise`,
    },
    {
      tone: documentIssue ? 'err' : 'ok',
      label: 'Ciorna e la zi şi documentul e complet',
      detail: documentIssue ? documentIssue.message : 'la zi',
    },
  ]
}

const byVersion = (a: Output, b: Output) => a.version - b.version

export function draftDocuments(outputs: Output[]): Output[] {
  return outputs
    .filter((item) => item.kind === 'draft' && item.stage === 'piee_generate' && isDocx(item))
    .sort(byVersion)
}

export function isDocx(output: Output): boolean {
  return output.name.toLowerCase().endsWith('.docx')
}

export function latestOutput(outputs: Output[]): Output | null {
  return [...outputs].sort(byVersion).at(-1) ?? null
}

/** The workflow selects the current final once; newer outputs never change it in the UI. */
export function currentFinal(outputs: Output[], checks: ExportChecks | undefined): Output | null {
  return checks?.final
    ? (outputs.find((item) => item.id === checks.final?.output_id) ?? null)
    : null
}

/** The PDF rendered in the same run as the current final; the only thing Previzualizare opens. */
export function previewPdf(outputs: Output[], checks: ExportChecks | undefined): Output | null {
  const final = currentFinal(outputs, checks)
  if (!final) return null
  return (
    outputs.find((item) => item.media_type === 'application/pdf' && item.run_id === final.run_id) ??
    null
  )
}

export function latestOf(outputs: Output[], predicate: (item: Output) => boolean): Output | null {
  return outputs.filter(predicate).sort(byVersion).at(-1) ?? null
}
