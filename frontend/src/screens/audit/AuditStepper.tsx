import type { AuditDocuments } from '../../api/audit-types.ts'
import type { Field, Output } from '../../api/types.ts'
import { Stepper, type Step } from '../../ui/Nav.tsx'

export function AuditStepper({
  documents,
  fields,
  outputs,
}: {
  documents: AuditDocuments
  fields: Field[]
  outputs: Output[]
}) {
  const files = [...documents.files, documents.anexa, documents.measures].filter(
    (file) => file !== null,
  )
  const read = files.filter((file) => file.status === 'read').length
  const found = fields.filter((field) => field.presence === 'found').length
  const pending = fields.filter((field) => field.review === 'pending').length
  const draft = outputs.filter(
    (output) => output.kind === 'draft' && output.name.endsWith('.docx'),
  ).length
  const complete = [
    true,
    files.length > 0 && read === files.length,
    fields.length > 0 && found === fields.length,
    fields.length > 0 && pending === 0,
    draft > 0,
  ]
  const current = complete.findIndex((value) => !value)
  const labels = [
    ['Configurare', 'gata'],
    ['Documente', `${String(read)}/${String(files.length)}`],
    ['Extragere', `${String(found)}/${String(fields.length)}`],
    ['Revizuire', `${String(pending)} în aşteptare`],
    ['Raport Word', draft ? `ciornă ${String(draft)}` : '—'],
  ]
  const steps: Step[] = labels.map(([label, detail], index) => ({
    label,
    detail,
    state: complete[index] ? 'done' : index === current ? 'current' : 'todo',
  }))
  return (
    <Stepper
      steps={steps}
      progress={Math.max(0, Math.min(100, (current < 0 ? 4 : current - 1) * 25))}
    />
  )
}
