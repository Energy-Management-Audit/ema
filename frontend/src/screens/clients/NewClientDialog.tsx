import { useState } from 'react'
import { ApiProblem } from '../../api/client.ts'
import { clientsApi } from '../../api/clients.ts'
import type { ClientOverview } from '../../api/clients-types.ts'
import { navigate } from '../../app/navigate.ts'
import { clientHref } from '../../app/route.ts'
import { invalidate } from '../../state/resource.ts'
import { Button } from '../../ui/Button.tsx'
import { Dialog } from '../../ui/Dialog.tsx'
import { TextField } from '../../ui/Field.tsx'
import { FailureNotice } from '../../ui/Feedback.tsx'

export function NewClientDialog({
  clients,
  onClose,
}: {
  clients: ClientOverview[]
  onClose: () => void
}) {
  const [cui, setCui] = useState('')
  const [name, setName] = useState('')
  const [problem, setProblem] = useState<ApiProblem | null>(null)
  const [busy, setBusy] = useState(false)
  const digits = cui.replace(/\D/g, '')
  const duplicate = clients.find((item) => (item.cui ?? '').replace(/\D/g, '') === digits)
  const manual = problem?.code === 'anaf_missing' || problem?.code === 'anaf_unavailable'

  async function submit(useAnaf: boolean) {
    setBusy(true)
    setProblem(null)
    try {
      const client = useAnaf
        ? await clientsApi.createFromAnaf(cui)
        : await clientsApi.createClient(name.trim(), digits)
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
      setBusy(false)
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
          {problem?.code === 'client_exists' && duplicate ? (
            <Button
              height={36}
              onClick={() => {
                onClose()
                navigate(clientHref(duplicate.id))
              }}
            >
              Deschide clientul
            </Button>
          ) : manual ? (
            <Button
              height={36}
              disabled={!name.trim() || busy}
              loading={busy}
              onClick={() => {
                void submit(false)
              }}
            >
              Adaugă fără ANAF
            </Button>
          ) : (
            <Button
              height={36}
              disabled={digits.length < 2 || busy}
              loading={busy}
              onClick={() => {
                void submit(true)
              }}
            >
              Caută în ANAF
            </Button>
          )}
        </>
      }
      content={
        <div className="clients-dialog-fields">
          <label>
            CUI
            <TextField
              value={cui}
              placeholder="RO 12345678"
              onChange={(event) => {
                setCui(event.target.value)
              }}
            />
          </label>
          {manual && (
            <label>
              Denumire
              <TextField
                value={name}
                onChange={(event) => {
                  setName(event.target.value)
                }}
              />
            </label>
          )}
          {problem && (
            <FailureNotice
              title={problem.code === 'client_exists' ? 'Clientul există deja.' : problem.title}
              actions={null}
            >
              {problem.title}
            </FailureNotice>
          )}
        </div>
      }
    >
      Caută clientul după CUI.
    </Dialog>
  )
}
