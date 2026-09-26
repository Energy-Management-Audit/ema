import { useEffect, useRef, useState } from 'react'
import { api } from '../api/endpoints.ts'
import type { Field } from '../api/types.ts'
import { parseNumber } from '../lib/format.ts'
import { useJob } from '../state/job.tsx'
import { Button } from '../ui/Button'
import { TextField } from '../ui/Field'
import { ProblemNotice, STALE_CODES, useAction } from './actions.tsx'
import { DECISION_KEYS } from './JournalEntries.tsx'

function parse(field: Field, text: string): { value: string } | { error: string } {
  if (field.value_type === 'number') return parseNumber(text)
  if (field.value_type === 'year') {
    return /^\d{4}$/.test(text.trim()) ? { value: text.trim() } : { error: 'Anul nu este valid.' }
  }
  return text.trim() ? { value: text.trim() } : { error: 'Valoarea lipseşte.' }
}

/** The inline editor that writes a value by hand: a `correct` decision on the field's revision. */
export function ValueEditor({
  field,
  onDone,
  autoFocus = false,
  label,
}: {
  field: Field
  onDone: () => void
  autoFocus?: boolean
  label?: string
}) {
  const ctx = useJob()
  const [text, setText] = useState('')
  const [invalid, setInvalid] = useState<string | null>(null)
  const action = useAction()
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => {
    if (autoFocus) input.current?.focus()
  }, [autoFocus])
  const save = () => {
    const parsed = parse(field, text)
    if ('error' in parsed) {
      setInvalid(parsed.error)
      return
    }
    setInvalid(null)
    void action
      .run(
        async () => {
          await api.correct(ctx.jobId, field.id, parsed.value, field.revision ?? 1)
          ctx.refresh(...DECISION_KEYS)
        },
        (problem) => {
          if (STALE_CODES.has(problem.code)) ctx.refresh(...DECISION_KEYS)
        },
      )
      .then((ok) => {
        if (ok) onDone()
      })
  }
  return (
    <div className="value-editor">
      <form
        className="value-editor__line"
        onSubmit={(event) => {
          event.preventDefault()
          save()
        }}
      >
        <TextField
          ref={input}
          aria-label={label ?? field.label}
          figures={field.value_type !== 'text'}
          value={text}
          width={220}
          onChange={(event) => {
            setText(event.target.value)
          }}
        />
        {field.unit && <span className="value-editor__unit">{field.unit}</span>}
        <Button type="submit" height={30} loading={action.pending} disabled={action.pending}>
          Salvează
        </Button>
        <Button variant="secondary" height={30} onClick={onDone}>
          Renunţă
        </Button>
      </form>
      {invalid && (
        <span className="value-editor__invalid" role="alert">
          {invalid}
        </span>
      )}
      <ProblemNotice problem={action.problem} />
    </div>
  )
}
