import { useEffect, useRef, useState } from 'react'
import { watchSession, type ApiProblem } from '../api/client.ts'
import { api } from '../api/endpoints.ts'
import { invalidateJob, useResource } from '../state/resource.ts'
import { JobProvider } from '../state/job.tsx'
import { JobScreen } from '../screens/JobScreen.tsx'
import { BootFailure, NoJob, SessionClosed } from '../screens/States.tsx'
import { navigate } from './navigate.ts'
import { jobHref, parseRoute } from './route.ts'

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

function Home() {
  const jobs = useResource('jobs', () => api.jobs())
  const first = jobs.data?.find((job) => job.type === 'piee')
  useEffect(() => {
    if (first) navigate(jobHref(first.id, 'date'), true)
  }, [first])
  if (jobs.error) return <BootFailure problem={jobs.error} />
  if (jobs.data && !first) return <NoJob />
  return null
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
  const jobTab = route.name === 'job' ? `${route.jobId}/${route.tab}` : null
  useEffect(() => {
    // Entering a job and switching tab refetch the job and its checks (D4).
    if (route.name === 'job' && previous.current !== null && previous.current !== jobTab) {
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
      <JobProvider key={route.jobId} jobId={route.jobId}>
        <JobScreen tab={route.tab} field={route.field} />
      </JobProvider>
    )
  }
  return <Home />
}
