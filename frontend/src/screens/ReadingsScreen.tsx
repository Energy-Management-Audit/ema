import { useState } from 'react'
import { ApiProblem } from '../api/client.ts'
import { api } from '../api/endpoints.ts'
import { photoForField, readingGroups } from '../audit/readings.ts'
import { jobKey, invalidateJob, useResource } from '../state/resource.ts'
import { Button } from '../ui/Button'
import { FailureNotice } from '../ui/Feedback'
import { Content, Window } from '../ui/Shell'
import { SectionKey } from '../ui/Surface'
import { JobSidebar } from './JobSidebar.tsx'
import { ReadingRow } from './ReadingRow.tsx'
import './readings.css'

export function ReadingsScreen({ jobId, field }: { jobId: string; field: string | null }) {
  const job = useResource(jobKey(jobId, 'job'), () => api.job(jobId))
  const fields = useResource(jobKey(jobId, 'fields'), () => api.fields(jobId))
  const visit = useResource(jobKey(jobId, 'visit'), () => api.visit(jobId))
  const log = useResource(jobKey(jobId, 'log'), () => api.log(jobId))
  const checks = useResource(jobKey(jobId, 'checks'), () => api.checks(jobId))
  const [starting, setStarting] = useState(false)
  const [problem, setProblem] = useState<ApiProblem | null>(null)
  const refresh = () => {
    invalidateJob(jobId, 'job', 'fields', 'visit', 'log', 'checks')
  }
  const start = async () => {
    if (!job.data || starting) return
    setStarting(true)
    setProblem(null)
    try {
      await api.startReadings(jobId, job.data.revision)
      refresh()
    } catch (error) {
      setProblem(
        error instanceof ApiProblem
          ? error
          : new ApiProblem('request_error', 0, 'Cererea nu poate fi procesată.'),
      )
    } finally {
      setStarting(false)
    }
  }
  const count = checks.data?.readiness.blocking?.length ?? 0
  const groups = visit.data && fields.data ? readingGroups(fields.data, visit.data) : []
  return (
    <Window>
      <JobSidebar activeId={jobId} count={count} working={job.data?.state === 'running'} />
      <Content
        crumb={job.data ? `${job.data.client_slug} ${String(job.data.year ?? '')}` : ''}
        title="Măsurători"
        actions={
          <Button
            height={32}
            loading={starting}
            disabled={starting || !job.data}
            onClick={() => {
              void start()
            }}
          >
            Citeşte fotografiile
          </Button>
        }
      >
        <div className="readings-screen">
          {problem && (
            <FailureNotice title={problem.title} actions={null}>
              {problem.title}
            </FailureNotice>
          )}
          {Boolean(job.error || fields.error || visit.error || log.error || checks.error) && (
            <FailureNotice
              title="Nu am putut încărca măsurătorile"
              actions={
                <Button variant="secondary" height={30} onClick={refresh}>
                  Încearcă din nou
                </Button>
              }
            >
              Verifică lucrarea şi încearcă din nou.
            </FailureNotice>
          )}
          {(job.loading || fields.loading || visit.loading || log.loading || checks.loading) &&
            !fields.data && <p>Se încarcă…</p>}
          {groups.length === 0 && visit.data && <p>Nu sunt fotografii de măsurători.</p>}
          {groups.map((group) => (
            <section className="readings-group" key={group.id}>
              <SectionKey>{group.label}</SectionKey>
              {group.fields.length === 0 && <p>Nu sunt valori citite.</p>}
              {group.fields.map((item) => (
                <ReadingRow
                  key={item.id}
                  jobId={jobId}
                  field={item}
                  photo={visit.data ? photoForField(item, visit.data) : null}
                  decisions={log.data ?? []}
                  focus={field === item.id}
                  refresh={refresh}
                />
              ))}
            </section>
          ))}
        </div>
      </Content>
    </Window>
  )
}
