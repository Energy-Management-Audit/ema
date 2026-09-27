import type { VisitView } from './types.ts'

export type DocFile = {
  slot: string
  name: string
  kind: string
  size_bytes: number
  version: number
  slot_revision: number
  sha: string
  status: 'read' | 'reading' | 'needs_conversion' | 'scanned' | 'protected' | 'failed' | 'unread'
  item: number | null
  item_text: string | null
  error_code: string | null
  reason: string | null
}
export type AuditDocuments = {
  files: DocFile[]
  anexa: DocFile | null
  measures: DocFile | null
  checklist: { number: number; text: string; received: boolean }[] | null
  missing: number[]
  unclassified: string[]
  visit: VisitView | null
  runs: Record<'intake' | 'read' | 'visit' | 'measures', { state: string; current: boolean } | null>
}
export type OutlineNode = {
  id: string
  parent: string | null
  chapter: number
  number: string
  title: string
  kind: string
  status: 'missing' | 'ready' | 'drafted' | 'done' | 'later' | 'n/a' | 'n/a proposed'
  computed_status: 'missing' | 'ready' | 'drafted'
  stale: boolean
  reason: string | null
  changed_input: string | null
  applicability_reason: string | null
  awaits: string[]
  missing_facts: string[]
  revision: number
  note: { text: string; revision: number } | null
  answered: boolean
}
export type AuditOutline = {
  nodes: OutlineNode[]
  deadline: { value: string | null; revision: number }
  visit_date: string | null
  answered: number
  total: number
  written: number
  chapters: number
}
