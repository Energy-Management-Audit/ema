import { useState } from 'react'
import { Plus, Search } from 'lucide-react'
import { ApiProblem } from '../../api/client.ts'
import { clientsApi } from '../../api/clients.ts'
import type { ClientOverview } from '../../api/clients-types.ts'
import { api } from '../../api/endpoints.ts'
import { AppSidebar } from '../../app/AppSidebar.tsx'
import { matchesClient } from '../../clients/search.ts'
import { plural as roCount } from '../../lib/plural.ts'
import { invalidate, useResource } from '../../state/resource.ts'
import { Button } from '../../ui/Button.tsx'
import { EmptyState, FailureNotice } from '../../ui/Feedback.tsx'
import { TextField } from '../../ui/Field.tsx'
import { Window } from '../../ui/Shell.tsx'
import { ClientsTable } from './ClientsTable.tsx'
import { NewClientDialog } from './NewClientDialog.tsx'
import './clients.css'

const NOW = Date.now()

type Filter = 'all' | 'working' | 'missing' | 'old'

/** M1: design handoff screen component. */
export function ClientsScreen() {
  const clients = useResource('clientsOverview', clientsApi.clientsOverview)
  const overview = useResource('overview', api.overview)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const [dialog, setDialog] = useState(false)
  const year = new Date().getFullYear() - 1
  const all = (clients.data ?? [])
    .slice()
    .sort((a, b) => (a.name ?? '').localeCompare(b.name ?? '', 'ro'))
  const jobs = overview.data ?? []
  const counts = {
    all: all.length,
    working: all.filter((client) =>
      jobs.some((job) => job.client_slug === client.id && !job.finalized),
    ).length,
    missing: all.filter((client) => !client.annex_years.includes(year)).length,
    old: all.filter(
      (client) =>
        !client.anaf_refreshed_at ||
        NOW - new Date(client.anaf_refreshed_at).getTime() > 180 * 86400000,
    ).length,
  }
  const shown = all.filter(
    (client: ClientOverview) =>
      matchesClient(client, query) &&
      (filter === 'all' ||
        (filter === 'working' &&
          jobs.some((job) => job.client_slug === client.id && !job.finalized)) ||
        (filter === 'missing' && !client.annex_years.includes(year)) ||
        (filter === 'old' &&
          (!client.anaf_refreshed_at ||
            NOW - new Date(client.anaf_refreshed_at).getTime() > 180 * 86400000))),
  )
  const open = () => {
    setDialog(true)
  }
  return (
    <Window>
      <AppSidebar current="clients" />
      <section className="ema-content clients-screen">
        <header className="clients-screen__head">
          <div>
            <h1>Clienţi</h1>
            <p>
              {roCount(all.length, 'client', 'clienţi')} · {all.length - counts.missing} cu Anexa
              2–3 pentru {year}
            </p>
          </div>
          <div className="clients-screen__actions">
            <label className="clients-screen__search">
              <Search size={15} />
              <TextField
                aria-label="Caută clienţi"
                placeholder="Caută după nume, CUI sau POD"
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value)
                }}
              />
            </label>
            <Button height={32} icon={Plus} onClick={open}>
              Client nou după CUI
            </Button>
          </div>
        </header>
        <div className="clients-screen__tabs" role="tablist" aria-label="Filtre clienţi">
          {(
            [
              ['all', `Toţi ${String(counts.all)}`],
              ['working', `Cu lucrări în curs ${String(counts.working)}`],
              ['missing', `Fără anexă ${String(year)} ${String(counts.missing)}`],
              ['old', `Date ANAF vechi ${String(counts.old)}`],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={filter === id}
              onClick={() => {
                setFilter(id)
              }}
            >
              {label}
            </button>
          ))}
        </div>
        {clients.loading && !clients.data && <p className="app-loading">Se încarcă…</p>}
        {clients.error != null && (
          <FailureNotice
            title="Nu am putut încărca clienţii"
            actions={
              <Button
                variant="secondary"
                height={28}
                onClick={() => {
                  invalidate('clientsOverview')
                }}
              >
                Încearcă din nou
              </Button>
            }
          >
            {clients.error instanceof ApiProblem
              ? clients.error.title
              : 'Cererea nu poate fi procesată.'}
          </FailureNotice>
        )}
        {clients.data &&
          (shown.length > 0 ? (
            <ClientsTable clients={shown} jobs={jobs} year={year} />
          ) : (
            <EmptyState
              mark="brand"
              title="Niciun client nu se potriveşte."
              actions={<Button onClick={open}>Client nou după CUI</Button>}
            >
              Caută după alt nume sau adaugă clientul după CUI.
            </EmptyState>
          ))}
      </section>
      {dialog && (
        <NewClientDialog
          clients={all}
          onClose={() => {
            setDialog(false)
          }}
        />
      )}
    </Window>
  )
}
