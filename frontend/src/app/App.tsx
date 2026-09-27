import { useEffect, useRef, useState } from 'react'
import { watchSession, type ApiProblem } from '../api/client.ts'
import { api } from '../api/endpoints.ts'
import { invalidateJob, useResource } from '../state/resource.ts'
import { JobProvider } from '../state/job.tsx'
import { JobScreen } from '../screens/JobScreen.tsx'
import { AuditJobScreen } from '../screens/audit/AuditJobScreen.tsx'
import { ClientsScreen } from '../screens/clients/ClientsScreen.tsx'
import { ClientScreen } from '../screens/clients/ClientScreen.tsx'
import { HomeScreen } from '../screens/home/HomeScreen.tsx'
import { InvoiceJobScreen } from '../screens/invoices/InvoiceJobScreen.tsx'
import { ReportingScreen } from '../screens/reporting/ReportingScreen.tsx'
import { SettingsScreen } from '../screens/settings/SettingsScreen.tsx'
import { BootFailure, SessionClosed, problemTitle } from '../screens/States.tsx'
import { Button } from '../ui/Button.tsx'
import { FailureNotice } from '../ui/Feedback.tsx'
import { Content, Window } from '../ui/Shell.tsx'
import { AppSidebar } from './AppSidebar.tsx'
import { navigate } from './navigate.ts'
import { jobPath, parseRoute } from './route.ts'

function currentLocation(): string {
  return location.pathname + location.search
}

function useLocation(): string {
  const [where, setWhere] = useState(currentLocation)
  useEffect(() => {
    const update = () => {
      setWhere(currentLocation())
    }
    window.addEventListener('popstate', update)
    // Links are real <a href="/app/…">; a plain left click stays in the app.
    const click = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0) return
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
      const anchor = (event.target as Element | null)?.closest('a')
      const target = anchor?.getAttribute('href')
      if (!anchor || !target?.startsWith('/app/') || anchor.target) return
      event.preventDefault()
      navigate(target)
    }
    document.addEventListener('click', click)
    return () => {
      window.removeEventListener('popstate', update)
      document.removeEventListener('click', click)
    }
  }, [])
  return where
}

function JobRouteGuard({
  jobId,
  prefix,
  children,
}: {
  jobId: string
  prefix: string
  children: React.ReactNode
}) {
  const job = useResource(`${jobId}/job`, () => api.job(jobId))
  const mismatch = job.data?.type !== undefined && job.data.type !== prefix
  useEffect(() => {
    if (mismatch && job.data) navigate(jobPath(job.data), true)
  }, [mismatch, job.data])
  if (mismatch) return null
  if (!job.data) {
    return (
      <Window>
        <AppSidebar />
        <Content crumb="" title="Lucrare">
          {job.error ? (
            <FailureNotice
              title="Nu am putut încărca lucrarea"
              actions={
                <Button
                  variant="secondary"
                  height={32}
                  onClick={() => {
                    invalidateJob(jobId, 'job')
                  }}
                >
                  Încearcă din nou
                </Button>
              }
            >
              {problemTitle(job.error)}
            </FailureNotice>
          ) : (
            <p className="app-loading">Se încarcă…</p>
          )}
        </Content>
      </Window>
    )
  }
  return children
}

export function App({ bootProblem }: { bootProblem: ApiProblem | null }) {
  const where = useLocation()
  const [closed, setClosed] = useState(
    bootProblem?.code === 'session_required' || bootProblem?.code === 'csrf_required',
  )
  useEffect(() => {
    watchSession(() => {
      setClosed(true)
    })
  }, [])
  const [pathname = '', search = ''] = where.split(/(?=\?)/)
  const route = parseRoute(pathname, search)
  const previous = useRef<string | null>(null)
  const jobTab =
    route.name === 'job' || route.name === 'audit' ? `${route.jobId}/${route.tab}` : null
  useEffect(() => {
    // Entering a job and switching tab refetch the job and its checks (D4).
    if (
      (route.name === 'job' || route.name === 'audit') &&
      previous.current !== null &&
      previous.current !== jobTab
    ) {
      invalidateJob(route.jobId, 'job', 'checks')
    }
    previous.current = jobTab
  }, [jobTab, route])
  useEffect(() => {
    if (route.name === 'unknown') navigate('/app/', true)
  }, [route.name])

  if (closed) return <SessionClosed />
  if (bootProblem) return <BootFailure problem={bootProblem} />
  if (route.name === 'job') {
    return (
      <JobRouteGuard jobId={route.jobId} prefix="piee">
        <JobProvider key={route.jobId} jobId={route.jobId}>
          <JobScreen tab={route.tab} field={route.field} />
        </JobProvider>
      </JobRouteGuard>
    )
  }
  if (route.name === 'audit')
    return (
      <JobRouteGuard jobId={route.jobId} prefix="audit">
        <AuditJobScreen jobId={route.jobId} tab={route.tab} field={route.field} />
      </JobRouteGuard>
    )
  if (route.name === 'invoices')
    return (
      <JobRouteGuard jobId={route.jobId} prefix="invoices">
        <InvoiceJobScreen jobId={route.jobId} />
      </JobRouteGuard>
    )
  if (route.name === 'clients') return <ClientsScreen />
  if (route.name === 'client') return <ClientScreen clientId={route.clientId} tab={route.tab} />
  if (route.name === 'reporting') return <ReportingScreen />
  if (route.name === 'settings') return <SettingsScreen group={route.group} />
  return <HomeScreen />
}
