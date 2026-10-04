import type { ExportChecks, Field, Issue } from '../api/types.ts'

export const dataWarnings = (checks: ExportChecks | null | undefined): Issue[] =>
  checks?.readiness.warnings ?? []

/** The field an evidence record backs: by its own value first, then by one of its candidates.
 * A warning's two sources usually belong to two fields, so each source opens with its own. */
export function sourceField(fields: Field[], evidenceId: string): Field | undefined {
  return (
    fields.find((field) => field.evidence?.includes(evidenceId)) ??
    fields.find((field) =>
      field.alternatives?.some((candidate) => candidate.evidence.includes(evidenceId)),
    )
  )
}
