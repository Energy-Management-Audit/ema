import { useState } from 'react'
import { ApiProblem } from '../../api/client.ts'
import { clientsApi } from '../../api/clients.ts'
import type { ClientOverview } from '../../api/clients-types.ts'
import { navigate } from '../../app/navigate.ts'
import { clientHref } from '../../app/route.ts'
import { existingClient } from '../../clients/search.ts'
import { invalidate } from '../../state/resource.ts'
import { Button } from '../../ui/Button.tsx'
import { Dialog } from '../../ui/Dialog.tsx'
import { TextField } from '../../ui/Field.tsx'
import { FailureNotice } from '../../ui/Feedback.tsx'

/** M2: design handoff screen component. */
export function NewClientDialog({
  clients,
  onClose,
}: {
  clients: ClientOverview[]
  onClose: () => void
}) {
  const [name, setName] = useState('')
  const [cui, setCui] = useState('')
  const [problem, setProblem] = useState<ApiProblem | null>(null)
  const [pending, setPending] = useState<'anaf' | 'add' | null>(null)
  const digits = cui.replace(/\D/g, '')
  const duplicate = existingClient(clients, name, cui)
  const cuiTaken = existingClient(clients, '', cui) !== undefined
  const exists = duplicate !== undefined || problem?.code === 'client_exists'

  async function submit(useAnaf: boolean) {
    setPending(useAnaf ? 'anaf' : 'add')
    setProblem(null)
    try {
      const client = useAnaf
        ? await clientsApi.createFromAnaf(cui)
        : await clientsApi.createClient(name.trim(), digits || null)
      invalidate('clients', 'clientsOverview')
      onClose()
      navigate(clientHref(client.id))
    } catch (error) {
      setProblem(
        error instanceof ApiProblem
          ? error
          : new ApiProblem('request_error', 500, 'Cererea nu poate fi procesată.'),
      )
    } finally {
      setPending(null)
    }
  }

  return (
    <Dialog
      title="Client nou"
      onClose={onClose}
      actions={
        <>
          <Button variant="secondary" height={36} onClick={onClose}>
            Renunţă
          </Button>
          {digits.length >= 2 && !cuiTaken && (
            <Button
              variant="secondary"
              height={36}
              disabled={pending !== null}
              loading={pending === 'anaf'}
              onClick={() => {
                void submit(true)
              }}
            >
              Caută în ANAF
            </Button>
          )}
          {duplicate ? (
            <Button
              height={36}
              onClick={() => {
                onClose()
                navigate(clientHref(duplicate.id))
              }}
            >
              Deschide clientul
            </Button>
          ) : (
            <Button
              height={36}
              disabled={!name.trim() || pending !== null}
              loading={pending === 'add'}
              onClick={() => {
                void submit(false)
              }}
            >
              Adaugă clientul
            </Button>
          )}
        </>
      }
      content={
        <div className="clients-dialog-fields">
          <label>
            Denumire
            <TextField
              value={name}
              onChange={(event) => {
                setName(event.target.value)
              }}
            />
          </label>
          <label>
            CUI (opţional)
            <TextField
              value={cui}
              placeholder="RO 12345678"
              onChange={(event) => {
                setCui(event.target.value)
              }}
            />
          </label>
          {exists ? (
            <FailureNotice title="Clientul există deja." actions={null}>
              {null}
            </FailureNotice>
          ) : (
            problem && (
              <FailureNotice title={problem.title} actions={null}>
                {problem.title}
              </FailureNotice>
            )
          )}
        </div>
      }
    >
      Adaugă clientul după denumire. CUI-ul este opţional.
    </Dialog>
  )
}
