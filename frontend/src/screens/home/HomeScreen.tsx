import { useEffect } from 'react'
import { api } from '../../api/endpoints.ts'
import { navigate } from '../../app/navigate.ts'
import { jobHref } from '../../app/route.ts'
import { useResource } from '../../state/resource.ts'
import { BootFailure, NoJob } from '../States.tsx'

export function HomeScreen() {
  const jobs = useResource('jobs', api.jobs)
  const first = jobs.data?.find((job) => job.type === 'piee')
  useEffect(() => {
    if (first) navigate(jobHref(first.id, 'date'), true)
  }, [first])
  if (jobs.error) return <BootFailure problem={jobs.error} />
  if (jobs.data && !first) return <NoJob />
  return null
}
