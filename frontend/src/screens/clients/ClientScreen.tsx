import { useState } from 'react'
import { Plus } from 'lucide-react'
import { ApiProblem } from '../../api/client.ts'
import { clientsApi } from '../../api/clients.ts'
import { api } from '../../api/endpoints.ts'
import { AppSidebar } from '../../app/AppSidebar.tsx'
import { NewJobDialog } from '../../app/NewJobDialog.tsx'
import { navigate } from '../../app/navigate.ts'
import { clientHref } from '../../app/route.ts'
import type { ClientTab } from '../../app/route.ts'
import { jobLabel } from '../../app/sidebar.ts'
import { formatCui, statusLine } from '../../clients/format.ts'
import { invalidate, useResource } from '../../state/resource.ts'
import { Button } from '../../ui/Button.tsx'
import { FailureNotice } from '../../ui/Feedback.tsx'
import { TextField } from '../../ui/Field.tsx'
import { Content, Window } from '../../ui/Shell.tsx'
import { ContactCard, IdentificationCard } from './ClientCards.tsx'
import { ClientJobsTab, MemoryTable, SitesTab } from './ClientTabs.tsx'
import './clients.css'

export type ClientScreenProps = { clientId: string; tab: ClientTab }

export function ClientScreen({ clientId, tab }: ClientScreenProps) {
  const profile = useResource(`client/${clientId}/profile`, () => clientsApi.profile(clientId))
  const overview = useResource('overview', api.overview)
  const [newJob, setNewJob] = useState(false)
  const [editing, setEditing] = useState<'energy_manager' | 'contact' | null>(null)
  const [contactName, setContactName] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const client = profile.data?.client
  const jobs = (overview.data ?? [])
    .filter((job) => job.client_slug === clientId)
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
  async function refreshAnaf() {
    setRefreshing(true)
    setProblem(null)
    try {
      await clientsApi.refreshAnaf(clientId)
      invalidate(`client/${clientId}/profile`, 'clientsOverview')
    } catch (error) {
      setProblem(error instanceof ApiProblem ? error.title : 'Cererea nu poate fi procesată.')
    } finally {
      setRefreshing(false)
    }
  }
  async function saveContact() {
    if (!client || !editing || !contactName.trim()) return
    try {
      await clientsApi.patchClient(
        clientId,
        {
          contacts: [
            ...client.contacts,
            { id: crypto.randomUUID(), name: contactName.trim(), role: editing },
          ],
        },
        client.revision,
      )
      invalidate(`client/${clientId}/profile`)
      setEditing(null)
      setContactName('')
      setProblem(null)
    } catch (error) {
      if (error instanceof ApiProblem && error.code === 'stale_revision') {
        invalidate(`client/${clientId}/profile`)
        setProblem('Clientul a fost modificat între timp.')
      } else
        setProblem(error instanceof ApiProblem ? error.title : 'Cererea nu poate fi procesată.')
    }
  }
  const sourceYear = profile.data?.annexes[0]?.year ?? new Date().getFullYear() - 1
  return (
    <Window activity>
      <AppSidebar current="clients" />
      <Content
        crumb={
          <button
            className="client-crumb"
            type="button"
            onClick={() => {
              navigate('/app/clienti')
            }}
          >
            Clienţi · {formatCui(client?.cui)}
          </button>
        }
        title={profile.data?.identification?.name ?? client?.name ?? 'Clienţi'}
        actions={
          <>
            <Button
              variant="secondary"
              height={34}
              loading={refreshing}
              disabled={refreshing || !client?.cui}
              onClick={() => {
                void refreshAnaf()
              }}
            >
              Reîmprospătează din ANAF
            </Button>
            <Button
              height={34}
              icon={Plus}
              onClick={() => {
                setNewJob(true)
              }}
            >
              Lucrare nouă
            </Button>
          </>
        }
      >
        <div className="client-screen">
          <div className="client-screen__tabs" role="tablist" aria-label="Secţiuni client">
            {(
              [
                ['date', 'Date generale'],
                ['lucrari', `Lucrări ${String(jobs.length)}`],
                ['puncte', `Puncte de lucru ${String(client?.sites.length ?? 0)}`],
                ['memorie', `Memorie CUI/POD ${String(profile.data?.memory.length ?? 0)}`],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={tab === id}
                onClick={() => {
                  navigate(clientHref(clientId, id))
                }}
              >
                {label}
              </button>
            ))}
          </div>
          {profile.loading && !profile.data && <p className="app-loading">Se încarcă…</p>}
          {profile.error != null && (
            <FailureNotice
              title="Nu am putut încărca clientul"
              actions={
                <Button
                  variant="secondary"
                  height={28}
                  onClick={() => {
                    invalidate(`client/${clientId}/profile`)
                  }}
                >
                  Încearcă din nou
                </Button>
              }
            >
              {profile.error instanceof ApiProblem
                ? profile.error.title
                : 'Cererea nu poate fi procesată.'}
            </FailureNotice>
          )}
          {problem && (
            <FailureNotice title={problem} actions={null}>
              {problem}
            </FailureNotice>
          )}
          {profile.data && tab === 'date' && (
            <>
              <IdentificationCard profile={profile.data} />
              <div className="client-screen__contacts">
                <ContactCard
                  title="DATE PRIVIND MANAGERUL ENERGETIC"
                  name={profile.data.energy_manager?.name}
                  detail={profile.data.energy_manager ? 'manager energetic' : undefined}
                  missing="Nu e completat."
                  onComplete={() => {
                    setEditing('energy_manager')
                  }}
                />
                <ContactCard
                  title="PERSOANĂ DE CONTACT"
                  name={profile.data.contact_person?.name}
                  source={
                    profile.data.contact_person?.source === 'annex'
                      ? `Anexa 2–3 · ${String(sourceYear)}`
                      : undefined
                  }
                  missing={`Nu apare în Anexa 2–3 ${String(sourceYear)}. Apare în PIEE ca „n.d.” până o completezi.`}
                  onComplete={() => {
                    setEditing('contact')
                  }}
                />
              </div>
              {editing && (
                <div className="client-inline">
                  <TextField
                    aria-label="Nume contact"
                    value={contactName}
                    onChange={(event) => {
                      setContactName(event.target.value)
                    }}
                  />
                  <Button
                    height={28}
                    disabled={!contactName.trim()}
                    onClick={() => {
                      void saveContact()
                    }}
                  >
                    Salvează
                  </Button>
                  <Button
                    variant="quiet"
                    height={28}
                    onClick={() => {
                      setEditing(null)
                    }}
                  >
                    Renunţă
                  </Button>
                </div>
              )}
              <MemoryTable profile={profile.data} jobs={jobs} />
            </>
          )}
          {profile.data && tab === 'lucrari' && (
            <ClientJobsTab jobs={jobs} clientName={client?.name ?? '—'} />
          )}
          {profile.data && tab === 'puncte' && <SitesTab profile={profile.data} />}
          {profile.data && tab === 'memorie' && <MemoryTable profile={profile.data} jobs={jobs} />}
        </div>
      </Content>
      <aside className="ema-activity client-activity">
        <div className="ema-activity__head">
          <span className="ema-activity__title">Lucrările clientului</span>
        </div>
        <div className="ema-activity__list">
          {jobs.map((job) => (
            <div className="client-activity__row" key={job.id}>
              <strong>{jobLabel(job)}</strong>
              <small>{statusLine(job)}</small>
              <span>{job.finalized ? 'final' : (job.blocking ?? 0) > 0 ? job.blocking : ''}</span>
            </div>
          ))}
        </div>
      </aside>
      <NewJobDialog
        open={newJob}
        clientId={clientId}
        onClose={() => {
          setNewJob(false)
        }}
      />
    </Window>
  )
}
