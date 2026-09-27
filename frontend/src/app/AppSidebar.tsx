import { useState } from 'react'
import { House, Table2, Users } from 'lucide-react'
import { ApiProblem } from '../api/client.ts'
import { api } from '../api/endpoints.ts'
import { navigate } from './navigate.ts'
import { jobPath } from './route.ts'
import { invalidate, useResource } from '../state/resource.ts'
import { Button } from '../ui/Button.tsx'
import { FailureNotice } from '../ui/Feedback.tsx'
import {
  NavClient,
  NavGroup,
  NavItem,
  NavJob,
  NewJobButton,
  Sidebar,
  SidebarFooter,
} from '../ui/Shell.tsx'
import { NewJobDialog } from './NewJobDialog.tsx'
import { finalizedJobs, finalizedLabel, groupInProgress, jobLabel, moreLabel } from './sidebar.ts'

export function AppSidebar({
  current,
  activeJobId,
  count,
  working,
}: {
  current?: 'home' | 'clients' | 'reporting'
  activeJobId?: string
  count?: number
  working?: boolean
}) {
  const overview = useResource('overview', api.overview)
  const clients = useResource('clients', api.clients)
  const [newJob, setNewJob] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const finished = finalizedJobs(overview.data ?? [])
  const shown = expanded ? finished : finished.slice(0, 1)
  const more = finished.length - shown.length
  return (
    <>
      <Sidebar
        action={
          <NewJobButton
            onClick={() => {
              setNewJob(true)
            }}
          >
            Lucrare nouă
          </NewJobButton>
        }
        footer={
          <SidebarFooter
            initials="AP"
            name="Auditor"
            onSettings={() => {
              navigate('/app/setari')
            }}
          />
        }
      >
        <div className="ema-sidebar__destinations">
          <NavItem
            icon={House}
            active={current === 'home'}
            onClick={() => {
              navigate('/app/')
            }}
          >
            Acasă
          </NavItem>
          <NavItem
            icon={Users}
            active={current === 'clients'}
            count={clients.data?.length}
            onClick={() => {
              navigate('/app/clienti')
            }}
          >
            Clienţi
          </NavItem>
          <NavItem
            icon={Table2}
            active={current === 'reporting'}
            onClick={() => {
              navigate('/app/raportare')
            }}
          >
            Raportare manager energetic
          </NavItem>
        </div>
        {((overview.loading && !overview.data) || (clients.loading && !clients.data)) && (
          <p className="app-loading">Se încarcă…</p>
        )}
        {overview.error != null && (
          <FailureNotice
            title="Nu am putut încărca lucrările"
            actions={
              <Button
                variant="secondary"
                height={26}
                onClick={() => {
                  invalidate('overview')
                }}
              >
                Încearcă din nou
              </Button>
            }
          >
            {overview.error instanceof ApiProblem
              ? overview.error.title
              : 'Cererea nu poate fi procesată.'}
          </FailureNotice>
        )}
        {clients.error != null && (
          <FailureNotice
            title="Nu am putut încărca clienţii"
            actions={
              <Button
                variant="secondary"
                height={26}
                onClick={() => {
                  invalidate('clients')
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
        <NavGroup title="ÎN LUCRU">
          {groupInProgress(overview.data ?? []).flatMap((group) => [
            <NavClient key={`client-${group.slug}`} color={group.color}>
              {group.name}
            </NavClient>,
            ...group.jobs.map((job) => {
              const active = job.id === activeJobId
              return (
                <NavJob
                  key={job.id}
                  active={active}
                  count={active && count && count > 0 ? count : undefined}
                  working={active ? working : job.state === 'running'}
                  onClick={() => {
                    navigate(jobPath(job))
                  }}
                >
                  {jobLabel(job)}
                </NavJob>
              )
            }),
          ])}
        </NavGroup>
        {finished.length > 0 && (
          <NavGroup title="FINALIZATE">
            {shown.map((job) => (
              <NavJob
                key={job.id}
                active={job.id === activeJobId}
                finished
                onClick={() => {
                  navigate(jobPath(job))
                }}
              >
                {finalizedLabel(job)}
              </NavJob>
            ))}
            {more > 0 && (
              <button
                className="ema-sidebar__more"
                type="button"
                onClick={() => {
                  setExpanded(true)
                }}
              >
                {moreLabel(more)}
              </button>
            )}
          </NavGroup>
        )}
      </Sidebar>
      <NewJobDialog
        open={newJob}
        onClose={() => {
          setNewJob(false)
        }}
      />
    </>
  )
}
