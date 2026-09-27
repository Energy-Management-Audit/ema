import { useEffect, useRef, useState } from 'react'
import { Download, Plus } from 'lucide-react'
import { ApiProblem } from '../../api/client.ts'
import { clientsApi } from '../../api/clients.ts'
import type { AnnexImport } from '../../api/clients-types.ts'
import { api, eventsPath } from '../../api/endpoints.ts'
import { reportingApi } from '../../api/reporting.ts'
import { AppSidebar } from '../../app/AppSidebar.tsx'
import { rel } from '../../lib/format.ts'
import { exceptionSources } from '../../reporting/view.ts'
import { roCount } from '../../clients/plural.ts'
import { invalidate, useResource } from '../../state/resource.ts'
import { Button } from '../../ui/Button.tsx'
import { EmaWidget, EmptyState, FailureNotice } from '../../ui/Feedback.tsx'
import { Content, Window } from '../../ui/Shell.tsx'
import { Card, SectionKey } from '../../ui/Surface.tsx'
import {
  AnnexImportDialog,
  ClientPickerDialog,
  ExceptionsBox,
  PreviewTable,
  YearChips,
} from './ReportingParts.tsx'
import './reporting.css'

export function ReportingScreen() {
  const clients = useResource('clientsOverview', clientsApi.clientsOverview)
  const runs = useResource('reportingRuns', reportingApi.runs)
  const latest = runs.data?.[0]
  const preview = useResource(
    latest?.state === 'ready' ? `reporting/${latest.id}/preview` : null,
    () => reportingApi.preview(latest?.id ?? ''),
  )
  const status = useResource(
    latest?.state === 'failed' ? `reporting/${latest.job_id}/status` : null,
    () => api.status(latest?.job_id ?? ''),
  )
  const indexedClients = (clients.data ?? []).filter((item) => item.annex_years.length > 0)
  const year = new Date().getFullYear() - 1
  const years = [year - 2, year - 1, year]
  const [selectedYears, setSelectedYears] = useState(years)
  const [selectedClientIds, setSelectedClientIds] = useState<string[] | null>(null)
  const chosen = selectedClientIds ?? indexedClients.map((item) => item.id)
  const [picker, setPicker] = useState(false)
  const [importResult, setImportResult] = useState<AnnexImport | null>(null)
  const [importError, setImportError] = useState<string | null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [importBusy, setImportBusy] = useState(false)
  const [runProblem, setRunProblem] = useState<string | null>(null)
  const [progress, setProgress] = useState('')
  const [expandedYear, setExpandedYear] = useState<number | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const selectedPreviewYear =
    expandedYear ??
    [...selectedYears]
      .reverse()
      .find((item) => (preview.data?.rows[String(item)]?.length ?? 0) > 0) ??
    selectedYears.at(-1) ??
    year

  useEffect(() => {
    if (!latest || latest.state !== 'running') return
    const source = new EventSource(eventsPath(latest.job_id))
    const progressHandler = (message: MessageEvent<string>) => {
      const event = JSON.parse(message.data) as { stage: string; payload: { message?: string } }
      if (event.stage === 'reporting') setProgress(event.payload.message ?? '')
    }
    const terminalHandler = (message: MessageEvent<string>) => {
      const event = JSON.parse(message.data) as { stage: string }
      if (event.stage !== 'reporting') return
      source.close()
      invalidate('reportingRuns', `reporting/${latest.id}/preview`)
    }
    source.addEventListener('stage_progress', progressHandler as EventListener)
    for (const kind of ['stage_finished', 'stage_failed', 'stage_cancelled'])
      source.addEventListener(kind, terminalHandler as EventListener)
    return () => {
      source.close()
    }
  }, [latest])

  async function importFiles(files: FileList | null) {
    if (!files?.length) return
    setImportBusy(true)
    setImportOpen(true)
    setImportError(null)
    setImportResult(null)
    try {
      const result = await clientsApi.importAnnexes(Array.from(files))
      setImportResult(result)
      invalidate('clientsOverview', 'clients')
    } catch (error) {
      setImportError(error instanceof ApiProblem ? error.title : 'Cererea nu poate fi procesată.')
    } finally {
      setImportBusy(false)
      if (input.current) input.current.value = ''
    }
  }
  async function generate() {
    setRunProblem(null)
    try {
      await reportingApi.startRun(
        [...selectedYears].sort((a, b) => a - b),
        chosen,
      )
      invalidate('reportingRuns')
    } catch (error) {
      setRunProblem(error instanceof ApiProblem ? error.title : 'Cererea nu poate fi procesată.')
    }
  }
  async function download() {
    if (!latest?.output_id) return
    try {
      const file = await api.output(latest.job_id, latest.output_id)
      const url = URL.createObjectURL(file)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = 'Raportare.xlsx'
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (error) {
      setRunProblem(error instanceof ApiProblem ? error.title : 'Cererea nu poate fi procesată.')
    }
  }
  const addAnnexes = () => {
    input.current?.click()
  }
  return (
    <Window activity>
      <AppSidebar current="reporting" />
      <Content
        crumb="Raport anual de activitate"
        title={`Raportare manager energetic ${String(selectedYears.length ? Math.min(...selectedYears) : years[0])}–${String(selectedYears.length ? Math.max(...selectedYears) : years.at(-1))}`}
        actions={
          <>
            <Button
              variant="secondary"
              icon={Download}
              height={34}
              disabled={latest?.state !== 'ready' || !latest.output_id}
              onClick={() => {
                void download()
              }}
            >
              Deschide registrul
            </Button>
            <Button
              variant="olive"
              height={34}
              disabled={
                selectedYears.length === 0 || chosen.length === 0 || latest?.state === 'running'
              }
              loading={latest?.state === 'running'}
              onClick={() => {
                void generate()
              }}
            >
              Generează raportul
            </Button>
          </>
        }
      >
        <div className="report-screen">
          {runs.loading && !runs.data && <p className="app-loading">Se încarcă…</p>}
          {runs.error != null && (
            <FailureNotice
              title="Nu am putut încărca raportările"
              actions={
                <Button
                  variant="secondary"
                  height={28}
                  onClick={() => {
                    invalidate('reportingRuns')
                  }}
                >
                  Încearcă din nou
                </Button>
              }
            >
              {runs.error instanceof ApiProblem
                ? runs.error.title
                : 'Cererea nu poate fi procesată.'}
            </FailureNotice>
          )}
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
          {runProblem && (
            <FailureNotice
              title="Raportul nu s-a generat"
              actions={
                <Button
                  variant="secondary"
                  height={28}
                  onClick={() => {
                    void generate()
                  }}
                >
                  Încearcă din nou
                </Button>
              }
            >
              {runProblem}
            </FailureNotice>
          )}
          {latest?.state === 'failed' && (
            <FailureNotice
              title="Raportul nu s-a generat"
              actions={
                <Button
                  variant="secondary"
                  height={28}
                  onClick={() => {
                    void generate()
                  }}
                >
                  Încearcă din nou
                </Button>
              }
            >
              {status.data?.runs.at(-1)?.error ?? ''}
            </FailureNotice>
          )}
          {preview.data && (
            <EmaWidget
              title={`${roCount(preview.data.read, 'anexă citită', 'anexe citite')} · ${String(exceptionSources(latest?.exceptions ?? []))} cu observaţii`}
            >
              Societăţile apar în anul în care au măsuri puse în funcţiune. Costurile lipsă rămân
              goale, nu zero.
            </EmaWidget>
          )}
          <div className="report-controls">
            <Card>
              <div className="report-control">
                <SectionKey>ANI</SectionKey>
                <YearChips
                  years={years}
                  selected={selectedYears}
                  counts={preview.data?.companies_per_year}
                  onToggle={(chosenYear) => {
                    setSelectedYears((current) =>
                      current.includes(chosenYear)
                        ? current.filter((one) => one !== chosenYear)
                        : [...current, chosenYear],
                    )
                  }}
                />
              </div>
            </Card>
            <Card>
              <div className="report-control">
                <SectionKey>CLIENŢI</SectionKey>
                <strong>
                  {chosen.length === indexedClients.length
                    ? `Toţi clienţii cu Anexa 2–3 (${String(indexedClients.length)})`
                    : roCount(chosen.length, 'client ales', 'clienţi aleşi')}
                </strong>
                <div>
                  <Button
                    variant="secondary"
                    height={30}
                    onClick={() => {
                      setPicker(true)
                    }}
                  >
                    Alege
                  </Button>
                  <Button variant="secondary" height={30} icon={Plus} onClick={addAnnexes}>
                    Adaugă anexe
                  </Button>
                </div>
              </div>
            </Card>
          </div>
          <input
            ref={input}
            type="file"
            accept=".xls,.xlsx"
            multiple
            hidden
            onChange={(event) => {
              void importFiles(event.target.files)
            }}
          />
          {latest?.state === 'running' && (
            <p className="report-progress">Se lucrează · {progress}</p>
          )}
          {!latest && !runs.loading && (
            <EmptyState
              mark="brand"
              title="Registrul nu a fost generat încă"
              actions={<Button onClick={addAnnexes}>Adaugă anexe</Button>}
            >
              Adaugă anexele primite, alege anii şi clienţii, apoi generează registrul.
            </EmptyState>
          )}
          {preview.data && (
            <>
              <PreviewTable
                preview={preview.data}
                year={selectedPreviewYear}
                years={selectedYears}
                onYearChange={setExpandedYear}
              />
              <ExceptionsBox exceptions={latest?.exceptions ?? []} clients={clients.data ?? []} />
            </>
          )}
        </div>
      </Content>
      <aside className="ema-activity report-activity">
        <div className="ema-activity__head">
          <span className="ema-activity__title">Ce s-a întâmplat</span>
        </div>
        <div className="ema-activity__list">
          {importResult && (
            <>
              <div>
                <strong>
                  {roCount(importResult.imported.length, 'anexă adăugată', 'anexe adăugate')}
                </strong>
                <small>
                  acum ·{' '}
                  {roCount(
                    importResult.imported.length + importResult.ignored.length,
                    'fişier',
                    'fişiere',
                  )}
                </small>
              </div>
              {importResult.ignored.length > 0 && (
                <div>
                  <strong>
                    {roCount(importResult.ignored.length, 'fişier ignorat', 'fişiere ignorate')}
                  </strong>
                  <small>
                    {[...new Set(importResult.ignored.map((item) => item.reason))].join(' · ')}
                  </small>
                </div>
              )}
            </>
          )}
          {preview.data && (
            <div>
              <strong>{roCount(preview.data.read, 'anexă citită', 'anexe citite')}</strong>
              <small>{latest ? rel(latest.created_at) : ''}</small>
            </div>
          )}
          <div>
            <strong>Registru de control</strong>
            <small>SHA-256 · celulele folosite pe fiecare sursă</small>
          </div>
        </div>
      </aside>
      {picker && (
        <ClientPickerDialog
          clients={indexedClients}
          selected={chosen}
          onDone={(ids) => {
            setSelectedClientIds(ids)
            setPicker(false)
          }}
          onClose={() => {
            setPicker(false)
          }}
        />
      )}
      {importOpen && !importBusy && (
        <AnnexImportDialog
          result={importResult}
          error={importError}
          onClose={() => {
            setImportOpen(false)
          }}
        />
      )}
    </Window>
  )
}
