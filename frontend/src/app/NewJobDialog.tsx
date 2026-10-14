import { useId, useState } from 'react'
import { Plus } from 'lucide-react'
import { ApiProblem } from '../api/client.ts'
import { clientsApi } from '../api/clients.ts'
import { api } from '../api/endpoints.ts'
import { clientLabel, clientMatches, offersNewClient } from '../clients/search.ts'
import { invalidate, useResource } from '../state/resource.ts'
import { Button } from '../ui/Button.tsx'
import { Choice, Dialog } from '../ui/Dialog.tsx'
import { TextField } from '../ui/Field.tsx'
import { FailureNotice } from '../ui/Feedback.tsx'
import { Icon } from '../ui/Icon.tsx'
import { ListRow } from '../ui/Rows.tsx'
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
  // The chosen client: an existing id, or the name of one to create with the job.
  const [chosen, setChosen] = useState<{ id: string } | { name: string } | null>(
    clientId ? { id: clientId } : null,
  )
  // null until the user types: the field then shows the preselected client's name.
  const [typed, setTyped] = useState<string | null>(null)
  const listId = useId()
  const [year, setYear] = useState(String(new Date().getFullYear()))
  const [submitting, setSubmitting] = useState(false)
  const [problem, setProblem] = useState<ApiProblem | null>(null)
  const all = clients.data ?? []
  const chosenClient =
    chosen && 'id' in chosen ? all.find((item) => item.id === chosen.id) : undefined
  const text = typed ?? (chosenClient ? clientLabel(chosenClient) : '')
  const matches = clientMatches(all, text)
  const offerNew = offersNewClient(all, text)
  const valid = selectedType !== null && chosen !== null && /^\d{4}$/.test(year)
  const submit = async () => {
    if (!valid || submitting) return
    setSubmitting(true)
    setProblem(null)
    try {
      let client: string
      if ('id' in chosen) {
        client = chosen.id
      } else {
        const created = await clientsApi.createClient(chosen.name, null)
        // The client stays if the job fails below; a retry then picks it instead of adding again.
        setChosen({ id: created.id })
        invalidate('clients', 'clientsOverview')
        client = created.id
      }
      const result = await api.createJob(selectedType, client, Number(year))
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
            <div className="new-job-dialog__client">
              <label className="new-job-dialog__field">
                Client
                <TextField
                  role="combobox"
                  aria-expanded={matches.length > 0 || offerNew}
                  aria-controls={listId}
                  aria-autocomplete="list"
                  autoComplete="off"
                  placeholder="Caută sau adaugă clientul"
                  value={text}
                  onChange={(event) => {
                    setTyped(event.target.value)
                    setChosen(null)
                  }}
                />
              </label>
              {(matches.length > 0 || offerNew) && (
                <div id={listId} role="listbox" className="new-job-dialog__list">
                  {matches.map((client) => {
                    const selected = chosen !== null && 'id' in chosen && chosen.id === client.id
                    const pick = () => {
                      setChosen({ id: client.id })
                      setTyped(clientLabel(client))
                    }
                    return (
                      <ListRow
                        key={client.id}
                        role="option"
                        tabIndex={0}
                        selected={selected}
                        className="new-job-dialog__row"
                        onClick={pick}
                        onKeyDown={(event) => {
                          if (event.key !== 'Enter' && event.key !== ' ') return
                          event.preventDefault()
                          pick()
                        }}
                      >
                        <span className="new-job-dialog__row-name">{clientLabel(client)}</span>
                        {client.cui && (
                          <span className="new-job-dialog__row-cui">{client.cui}</span>
                        )}
                      </ListRow>
                    )
                  })}
                  {offerNew && (
                    <ListRow
                      role="option"
                      tabIndex={0}
                      selected={chosen !== null && 'name' in chosen}
                      className="new-job-dialog__row new-job-dialog__row--add"
                      onClick={() => {
                        setChosen({ name: text.trim() })
                      }}
                      onKeyDown={(event) => {
                        if (event.key !== 'Enter' && event.key !== ' ') return
                        event.preventDefault()
                        setChosen({ name: text.trim() })
                      }}
                    >
                      <Icon icon={Plus} size={13} stroke={1.9} />
                      <span className="new-job-dialog__row-name">
                        Adaugă clientul „{text.trim()}”
                      </span>
                    </ListRow>
                  )}
                </div>
              )}
            </div>
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
