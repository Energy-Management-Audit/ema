import type { Field } from '../api/types.ts'

export type ReviewFilter = 'pending' | 'uncertain' | 'accepted'
export function scalar(value: unknown): string {
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  if (typeof value === 'boolean') return value ? 'da' : 'nu'
  return '—'
}
export const photoField = (field: Field) =>
  field.key.startsWith('meter.') || field.key.startsWith('thermal.')
export const reviewFields = (fields: Field[]) => fields.filter((field) => !photoField(field))
export const pending = (field: Field) =>
  field.review === 'pending' || (field.required && field.presence !== 'found')
export const uncertain = (field: Field) =>
  pending(field) && ['partial', 'conflict', 'none'].includes(field.confidence ?? 'none')
export const accepted = (field: Field) =>
  field.review === 'accepted' || field.review === 'corrected'
export const decided = (field: Field) => accepted(field) || field.review === 'rejected'
export function filterFields(fields: Field[], filter: ReviewFilter): Field[] {
  return fields.filter((field) =>
    filter === 'pending'
      ? pending(field)
      : filter === 'uncertain'
        ? uncertain(field)
        : decided(field),
  )
}
export const exactBatch = (fields: Field[]): [string, number][] =>
  fields
    .filter(
      (field) =>
        field.review === 'pending' &&
        field.confidence === 'exact' &&
        field.value !== null &&
        field.value !== undefined &&
        field.presence === 'found' &&
        ['supplied', 'extracted', 'calculated'].includes(field.state) &&
        !field.needs_confirmation,
    )
    .map((field) => [field.id, field.revision ?? 0])

export function groupByChapter(fields: Field[]): [string, Field[]][] {
  const groups = new Map<string, Field[]>()
  for (const field of fields) {
    const chapter = field.chapter?.match(/^ch\d+/)?.[0] ?? ''
    groups.set(chapter, [...(groups.get(chapter) ?? []), field])
  }
  return [...groups]
}
