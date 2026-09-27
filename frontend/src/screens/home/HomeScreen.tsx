import { useEffect, useRef, useState } from 'react'
import { Plus } from 'lucide-react'
import { ApiProblem } from '../../api/client.ts'
import { api } from '../../api/endpoints.ts'
import { settingsApi } from '../../api/settings.ts'
import { updateApi } from '../../api/update.ts'
import { NewJobDialog } from '../../app/NewJobDialog.tsx'
import { AppSidebar } from '../../app/AppSidebar.tsx'
import { invalidate, useResource } from '../../state/resource.ts'
import { Button } from '../../ui/Button.tsx'
import { EmaWidget, EmptyState, FailureNotice } from '../../ui/Feedback.tsx'
import { Window } from '../../ui/Shell.tsx'
import { SectionKey } from '../../ui/Surface.tsx'
import { attentionLine } from '../../home/count-words.ts'
import { formatDay } from '../../home/format.ts'
import { HomeJobRow } from './HomeJobRow.tsx'
import { BackupWidget } from './BackupWidget.tsx'
import './home.css'

export function HomeScreen() {
  const overview = useResource('overview', api.overview)
  const settings = useResource('settings', settingsApi.settings)
  const update = useResource('update', updateApi.status)
  const refreshCachedUpdate = useRef(Boolean(update.data))
  useEffect(() => {
    if (refreshCachedUpdate.current) invalidate('update')
  }, [])
  const updateLink = update.data?.download_url ?? update.data?.page_url
  const [newJobType, setNewJobType] = useState<'audit' | null | undefined>(undefined)
  const [completedBackup, setCompletedBackup] = useState<string | null>(null)
  const jobs = (overview.data ?? [])
    .filter((job) => !job.finalized && job.type !== 'reporting')
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
  const blocking = jobs.filter((job) => (job.blocking ?? 0) > 0).length
  return (
    <Window>
      <AppSidebar current="home" />
      <main className="home-screen">
        <div className="home-screen__inner">
          <p className="home-screen__date">{formatDay(new Date())}</p>
          <div className="home-screen__heading">
            <h1>Bine ai revenit.</h1>
            <Button
              icon={Plus}
              onClick={() => {
                setNewJobType(null)
              }}
            >
              Lucrare nouă
            </Button>
          </div>
          {overview.loading && !overview.data && <p className="home-screen__muted">Se încarcă…</p>}
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
          {overview.data && overview.data.length === 0 ? (
            <EmptyState
              mark="brand"
              title="Începe cu un audit"
              actions={
                <Button
                  onClick={() => {
                    setNewJobType('audit')
                  }}
                >
                  Lucrare nouă
                </Button>
              }
              footnote="PDF · DOCX · XLSX · max. 100 MB"
            >
              Alege clientul şi anul, apoi adaugi dosarul primit de la client. Facturile şi PIEE vin
              după.
            </EmptyState>
          ) : overview.data ? (
            <>
              <div className="home-screen__section">
                <SectionKey>UNDE AI RĂMAS</SectionKey>
                {jobs.length > 0 && <span>{attentionLine(jobs.length, blocking)}</span>}
              </div>
              <div className="home-screen__jobs">
                {jobs.map((job) => (
                  <HomeJobRow key={job.id} job={job} />
                ))}
              </div>
              {completedBackup ? (
                <p className="home-screen__muted">Copia e făcută: {completedBackup}</p>
              ) : (
                settings.data?.backup.due && (
                  <BackupWidget backup={settings.data.backup} onComplete={setCompletedBackup} />
                )
              )}
              {settings.error != null && (
                <FailureNotice
                  title="Nu am putut încărca setările"
                  actions={
                    <Button
                      variant="secondary"
                      height={26}
                      onClick={() => {
                        invalidate('settings')
                      }}
                    >
                      Încearcă din nou
                    </Button>
                  }
                >
                  {settings.error instanceof ApiProblem
                    ? settings.error.title
                    : 'Cererea nu poate fi procesată.'}
                </FailureNotice>
              )}
            </>
          ) : null}
          {update.data?.newer && update.data.latest && updateLink && (
            <div className="home-screen__backup">
              <EmaWidget
                title={`Există o versiune nouă a Ema (${update.data.latest})`}
                actions={
                  <a
                    className="ema-btn ema-btn--secondary ema-btn--h32 home-screen__update-link"
                    href={updateLink}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Descarcă
                  </a>
                }
              >
                {`Versiunea ${update.data.latest} este disponibilă.`}
              </EmaWidget>
            </div>
          )}
        </div>
      </main>
      <NewJobDialog
        open={newJobType !== undefined}
        type={newJobType ?? undefined}
        onClose={() => {
          setNewJobType(undefined)
        }}
      />
    </Window>
  )
}
