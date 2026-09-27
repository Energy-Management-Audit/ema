import { useState } from 'react'
import { ApiProblem } from '../api/client.ts'
import { api } from '../api/endpoints.ts'
import { invalidate, useResource } from '../state/resource.ts'
import { Button } from '../ui/Button.tsx'
import { Choice, Dialog } from '../ui/Dialog.tsx'
import { Select, TextField } from '../ui/Field.tsx'
import { FailureNotice } from '../ui/Feedback.tsx'
import { navigate } from './navigate.ts'
import { auditHref, invoicesHref, jobHref } from './route.ts'

type JobType = 'audit' | 'piee' | 'invoices'

export function NewJobDialog({
  open,
  onClose,
  type,
  clientId,
}: {
  open: boolean
  onClose: () => void
  type?: JobType
  clientId?: string
}) {
  if (!open) return null
  return (
    <NewJobDialogContent
      key={`${type ?? ''}/${clientId ?? ''}`}
      onClose={onClose}
      type={type}
      clientId={clientId}
    />
  )
}

function NewJobDialogContent({
  onClose,
  type,
  clientId,
}: {
  onClose: () => void
  type?: JobType
  clientId?: string
}) {
  const clients = useResource('clients', api.clients)
  const [selectedType, setSelectedType] = useState<JobType | null>(type ?? null)
  const [selectedClient, setSelectedClient] = useState(clientId ?? '')
  const [year, setYear] = useState(String(new Date().getFullYear()))
  const [submitting, setSubmitting] = useState(false)
  const [problem, setProblem] = useState<ApiProblem | null>(null)
  const valid = selectedType !== null && selectedClient !== '' && /^\d{4}$/.test(year)
  const submit = async () => {
    if (!valid || submitting) return
    setSubmitting(true)
    setProblem(null)
    try {
      const result = await api.createJob(selectedType, selectedClient, Number(year))
      invalidate('jobs', 'overview')
      onClose()
      navigate(
        selectedType === 'piee'
          ? jobHref(result.id, 'documente')
          : selectedType === 'audit'
            ? auditHref(result.id, 'documente')
            : invoicesHref(result.id),
      )
    } catch (error) {
      setProblem(
        error instanceof ApiProblem
          ? error
          : new ApiProblem('request_error', 0, 'Cererea nu poate fi procesată.'),
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog
      title="Lucrare nouă"
      onClose={onClose}
      content={
        <div className="new-job-dialog">
          {clients.data?.length === 0 ? (
            <p>
              Adaugă întâi clientul.{' '}
              <a href="/app/clienti" onClick={onClose}>
                Clienţi
              </a>
            </p>
          ) : (
            <>
              <div className="new-job-dialog__choices">
                <Choice
                  name="job-type"
                  checked={selectedType === 'audit'}
                  onSelect={() => {
                    setSelectedType('audit')
                  }}
                  title="Audit energetic"
                  detail=""
                />
                <Choice
                  name="job-type"
                  checked={selectedType === 'piee'}
                  onSelect={() => {
                    setSelectedType('piee')
                  }}
                  title="PIEE"
                  detail=""
                />
                <Choice
                  name="job-type"
                  checked={selectedType === 'invoices'}
                  onSelect={() => {
                    setSelectedType('invoices')
                  }}
                  title="Facturi"
                  detail=""
                />
              </div>
              <label className="new-job-dialog__field">
                Client
                <Select
                  placeholder="Alege clientul"
                  value={selectedClient}
                  onChange={(event) => {
                    setSelectedClient(event.target.value)
                  }}
                >
                  {[...(clients.data ?? [])]
                    .sort((a, b) => (a.name ?? a.id).localeCompare(b.name ?? b.id))
                    .map((client) => (
                      <option key={client.id} value={client.id}>
                        {client.name ?? client.id}
                      </option>
                    ))}
                </Select>
              </label>
              <label className="new-job-dialog__field">
                Anul
                <TextField
                  figures
                  inputMode="numeric"
                  maxLength={4}
                  value={year}
                  onChange={(event) => {
                    setYear(event.target.value)
                  }}
                />
              </label>
            </>
          )}
          {problem && (
            <FailureNotice title="Nu am putut crea lucrarea" actions={null}>
              {problem.title}
            </FailureNotice>
          )}
        </div>
      }
      actions={
        <>
          <Button variant="secondary" onClick={onClose}>
            Renunţă
          </Button>
          <Button
            disabled={!valid || submitting}
            loading={submitting}
            onClick={() => {
              void submit()
            }}
          >
            Creează lucrarea
          </Button>
        </>
      }
    >
      Alege tipul lucrării şi clientul.
    </Dialog>
  )
}
