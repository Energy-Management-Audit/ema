import { useState } from 'react'
import type { Field } from '../api/types.ts'
import { fieldLabel } from '../piee/labels.ts'
import { useJob } from '../state/job.tsx'
import { Button } from '../ui/Button'
import { Status } from '../ui/Chip'
import { FieldReviewRow } from '../ui/Review'
import { ValueEditor } from './ValueEditor.tsx'

/** A value no document holds (3c): ask the client or write it by hand. */
export function MissingRow({ field }: { field: Field }) {
  const { job } = useJob()
  const [writing, setWriting] = useState(false)
  const label = fieldLabel(field.key, field.label, job.data?.year ?? null)
  return (
    <div data-testid={`missing-row-${field.id}`}>
      <FieldReviewRow
        label={label}
        status={<Status tone="warn">lipseşte</Status>}
        value={
          writing ? (
            <ValueEditor
              field={field}
              label={label}
              autoFocus
              onDone={() => {
                setWriting(false)
              }}
            />
          ) : (
            <span className="missing-row__text">
              nu s-a găsit în documente — cere-o clientului sau scrie-o manual
            </span>
          )
        }
        actions={
          writing ? undefined : (
            <Button
              variant="secondary"
              height={28}
              onClick={() => {
                setWriting(true)
              }}
            >
              Scrie valoarea
            </Button>
          )
        }
      />
    </div>
  )
}
