import { useState } from 'react'
import type { ClientProfile, Site } from '../../api/clients-types.ts'
import type { JobOverview } from '../../api/types.ts'
import { clientsApi } from '../../api/clients.ts'
import { ApiProblem } from '../../api/client.ts'
import { navigate } from '../../app/navigate.ts'
import { jobPath } from '../../app/route.ts'
import { jobLabel } from '../../app/sidebar.ts'
import { statusLine } from '../../clients/format.ts'
import { formatDate } from '../../lib/format.ts'
import { invalidate } from '../../state/resource.ts'
import { Button } from '../../ui/Button.tsx'
import { FailureNotice } from '../../ui/Feedback.tsx'
import { TextField } from '../../ui/Field.tsx'
import { SectionKey } from '../../ui/Surface.tsx'
import { DeleteJobDialog } from './DeleteJobDialog.tsx'

export function MemoryTable({ profile, jobs }: { profile: ClientProfile; jobs: JobOverview[] }) {
  return (
    <section className="client-section">
      <SectionKey>MEMORIE CUI/POD · DIN FACTURI CONFIRMATE</SectionKey>
      {profile.memory.length === 0 ? (
        <p>Nicio confirmare din facturi încă.</p>
      ) : (
        <div className="client-list">
          <div className="client-list__head">
            <span>POD / CUI</span>
            <span>CONFIRMAT ÎN</span>
            <span>STARE</span>
          </div>
          {profile.memory.map((item, index) => {
            const job = jobs.find((one) => one.id === item.job_id)
            return (
              <div className="client-list__row" key={`${item.identifier}-${String(index)}`}>
                <span className="ema-figures">{item.identifier}</span>
                <button
                  type="button"
                  onClick={() => {
                    if (job) navigate(jobPath(job))
                  }}
                >
                  {job ? jobLabel(job) : item.job_id} · {formatDate(item.confirmed_at)}
                </button>
                <span className={item.active ? 'client-status--ok' : ''}>
                  {item.active ? 'activ' : 'retras'}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}

export function SitesTab({ profile }: { profile: ClientProfile }) {
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState('')
  const [address, setAddress] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  async function save(sites: Site[]) {
    try {
      await clientsApi.patchClient(profile.client.id, { sites }, profile.client.revision)
      invalidate(`client/${profile.client.id}/profile`)
      setEditing(false)
      setName('')
      setAddress('')
      setProblem(null)
    } catch (error) {
      if (error instanceof ApiProblem && error.code === 'stale_revision')
        invalidate(`client/${profile.client.id}/profile`)
      setProblem(error instanceof ApiProblem ? error.title : 'Cererea nu poate fi procesată.')
    }
  }
  return (
    <section className="client-section">
      <SectionKey>PUNCTE DE LUCRU</SectionKey>
      {profile.client.sites.length === 0 && <p>Niciun punct de lucru.</p>}
      <div className="client-list">
        {profile.client.sites.map((site) => (
          <div className="client-list__row" key={site.id}>
            <span>
              <strong>{site.name}</strong>
              <small>{site.address}</small>
            </span>
            <Button
              variant="quiet"
              height={28}
              onClick={() => {
                void save(profile.client.sites.filter((one) => one.id !== site.id))
              }}
            >
              Scoate
            </Button>
          </div>
        ))}
      </div>
      {editing ? (
        <div className="client-inline">
          <TextField
            aria-label="Denumire"
            placeholder="Denumire"
            value={name}
            onChange={(event) => {
              setName(event.target.value)
            }}
          />
          <TextField
            aria-label="Adresă"
            placeholder="Adresă"
            value={address}
            onChange={(event) => {
              setAddress(event.target.value)
            }}
          />
          <Button
            height={28}
            disabled={!name.trim()}
            onClick={() => {
              void save([
                ...profile.client.sites,
                { id: crypto.randomUUID(), name: name.trim(), address: address.trim() || null },
              ])
            }}
          >
            Salvează
          </Button>
          <Button
            variant="quiet"
            height={28}
            onClick={() => {
              setEditing(false)
            }}
          >
            Renunţă
          </Button>
        </div>
      ) : (
        <Button
          variant="secondary"
          height={30}
          onClick={() => {
            setEditing(true)
          }}
        >
          Adaugă punct de lucru
        </Button>
      )}
      {problem && (
        <FailureNotice title="Nu am putut salva punctul de lucru" actions={null}>
          {problem}
        </FailureNotice>
      )}
    </section>
  )
}

export function ClientJobsTab({ jobs, clientName }: { jobs: JobOverview[]; clientName: string }) {
  const [deleting, setDeleting] = useState<JobOverview | null>(null)
  return (
    <section className="client-section">
      <SectionKey>LUCRĂRI</SectionKey>
      <div className="client-list">
        {jobs.map((job) => (
          <div className="client-list__row" key={job.id}>
            <span>
              <strong>{jobLabel(job)}</strong>
              <small>{statusLine(job)}</small>
            </span>
            <span>
              <Button
                variant="secondary"
                height={28}
                onClick={() => {
                  navigate(jobPath(job))
                }}
              >
                Deschide
              </Button>
              <Button
                variant="quiet"
                height={28}
                onClick={() => {
                  setDeleting(job)
                }}
              >
                Şterge
              </Button>
            </span>
          </div>
        ))}
      </div>
      {jobs.length === 0 && <p>Nicio lucrare.</p>}
      {deleting && (
        <DeleteJobDialog
          job={deleting}
          clientName={clientName}
          onClose={() => {
            setDeleting(null)
          }}
        />
      )}
    </section>
  )
}
