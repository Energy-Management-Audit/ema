import { useEffect, useRef, useState } from 'react'
import { ApiProblem } from '../../api/client.ts'
import { api } from '../../api/endpoints.ts'
import { invoicesApi } from '../../api/invoices.ts'
import { download, useAction } from '../actions.tsx'
import { invalidate, jobKey, useResource } from '../../state/resource.ts'
import { JobProvider, useJob } from '../../state/job.tsx'
import { AppSidebar } from '../../app/AppSidebar.tsx'
import { invoiceView } from '../../invoices/view.ts'
import { Button } from '../../ui/Button.tsx'
import { EmaWidget, EmptyState, FailureNotice, ProgressBar } from '../../ui/Feedback.tsx'
import { Card, CardHeader } from '../../ui/Surface.tsx'
import { Content, Window } from '../../ui/Shell.tsx'
import { IdentityView } from './IdentityView.tsx'
import { InvoiceActivity } from './InvoiceActivity.tsx'
import { InvoiceTable } from './InvoiceTable.tsx'
import './invoices.css'

export type InvoiceJobScreenProps = { jobId: string }

export function InvoiceJobScreen({ jobId }: InvoiceJobScreenProps) {
  return (
    <JobProvider jobId={jobId}>
      <InvoiceJobContent />
    </JobProvider>
  )
}

function InvoiceJobContent() {
  const ctx = useJob()
  const { jobId } = ctx
  const { run, refresh } = ctx
  const slots = useResource(jobKey(jobId, 'slots'), () => api.slots(jobId))
  const ready =
    ctx.status.data?.runs.some(
      (run) => run.stage === 'invoices' && run.state === 'ready' && run.publication === 'current',
    ) ?? false
  const identity = useResource(ready ? jobKey(jobId, 'identity') : null, () =>
    invoicesApi.identity(jobId),
  )
  const batch = useResource(ready ? jobKey(jobId, 'invoices') : null, () =>
    invoicesApi.batch(jobId),
  )
  const action = useAction()
  const picker = useRef<HTMLInputElement>(null)
  const [replace, setReplace] = useState<string | null>(null)
  const [rejected, setRejected] = useState<{ file_name: string; reason: string }[]>([])
  const [openId, setOpenId] = useState<string | null>(null)
  const completedRun = run && run.state !== 'running' ? run.runId : null

  useEffect(() => {
    if (completedRun) refresh('invoices', 'identity', 'slots')
  }, [completedRun, refresh])

  const begin = async (stage: 'invoices' | 'invoices_workbook') => {
    const revision =
      stage === 'invoices_workbook' ? ctx.job.data?.revision : (await api.job(jobId)).revision
    if (revision === undefined) throw new ApiProblem('job_missing', 404, 'Lucrarea nu există.')
    const started = await api.startStage(jobId, stage, revision)
    ctx.follow(started.run_id, stage)
    ctx.refresh('job', 'status', 'checks', 'slots')
  }

  const pick = (slot: string | null = null) => {
    setReplace(slot)
    if (picker.current) {
      picker.current.value = ''
      picker.current.multiple = slot === null
      picker.current.click()
    }
  }

  const upload = (files: File[]) => {
    void action.run(async () => {
      const result = await invoicesApi.uploadInvoices(jobId, files, replace ?? undefined)
      setRejected(result.rejected)
      if (result.added.length) {
        ctx.refresh('slots', 'job', 'status', 'invoices', 'identity')
        await begin('invoices')
      }
    })
  }

  const remove = (slot: string) => {
    void action.run(async () => {
      const versions = await api.slotVersions(jobId, slot)
      const current = versions.at(-1)
      if (!current) throw new ApiProblem('file_missing', 404, 'Fişierul nu există.')
      await api.removeVersion(jobId, slot, current.version, current.slot_revision)
      ctx.refresh('slots', 'job', 'status', 'invoices', 'identity')
      const remaining = await api.slots(jobId)
      if (remaining.some((item) => item.startsWith('invoices/'))) await begin('invoices')
    })
  }

  const confirm = () => {
    if (!ctx.job.data || !identity.data) return
    void action.run(async () => {
      await invoicesApi.confirm(
        jobId,
        ctx.job.data?.client_slug ?? '',
        identity.data?.revision ?? 0,
      )
      ctx.refresh('job', 'status', 'fields', 'log', 'checks', 'invoices', 'identity')
      invalidate('overview')
    })
  }

  const undo = (decisionId: string) => {
    void action.run(async () => {
      await api.undo(jobId, decisionId)
      ctx.refresh('job', 'status', 'fields', 'log', 'checks', 'invoices', 'identity')
      invalidate('overview')
    })
  }

  const view = invoiceView({
    slots: slots.data ?? [],
    runs: [
      ...(ctx.status.data?.runs ?? []),
      ...(ctx.run?.state === 'running' && ctx.run.stage === 'invoices'
        ? [{ id: ctx.run.runId, stage: ctx.run.stage, state: ctx.run.state }]
        : []),
    ],
    confirmed: identity.data?.confirmed ?? null,
  })
  const year = ctx.job.data?.year ?? batch.data?.year ?? null
  const fileCount = (slots.data ?? []).filter((slot) => slot.startsWith('invoices/')).length
  const latest = ctx.status.data?.runs.filter((run) => run.stage === 'invoices').at(-1)
  const readingError = latest?.state === 'failed' ? latest.error : null
  const output = ctx.outputs.data?.findLast(
    (item) =>
      item.stage === 'invoices_workbook' &&
      item.name === 'Facturi.xlsx' &&
      ctx.status.data?.runs.some(
        (run) => run.id === item.run_id && run.state === 'ready' && run.publication === 'current',
      ),
  )
  const exportBlocked = !ctx.checks.data?.readiness.final_ok || ctx.run?.state === 'running'
  const exportReason = ctx.checks.data?.readiness.next?.[0] ?? 'Exportul nu este pregătit.'
  const firstLoading =
    (!ctx.job.data && !ctx.job.error) ||
    (!ctx.status.data && !ctx.status.error) ||
    (!slots.data && !slots.error) ||
    (ready && ((!identity.data && !identity.error) || (!batch.data && !batch.error)))
  const loadError =
    ctx.job.error || ctx.status.error || slots.error || (ready && (identity.error || batch.error))
  const failedTitle =
    view === 'table' ? 'Nu am putut încărca facturile' : 'Nu am putut încărca lotul de facturi'
  const readAgain = () => {
    void action.run(() => begin('invoices'))
  }
  const blocked = ctx.checks.data?.readiness.blocking?.length ?? 0

  return (
    <Window activity>
      <AppSidebar activeJobId={jobId} count={blocked} working={ctx.run?.state === 'running'} />
      <Content
        crumb={
          view === 'identity'
            ? `Facturi · ${String(fileCount)} PDF încărcate`
            : `${ctx.client.data?.name ?? ctx.job.data?.client_slug ?? ''} ${String(year ?? '')}`
        }
        title={view === 'identity' ? 'Al cui e acest lot?' : `Facturi ${String(year ?? '')}`}
        actions={
          view === 'table' && (
            <>
              <Button
                variant="secondary"
                height={34}
                onClick={() => {
                  pick()
                }}
              >
                Adaugă facturi
              </Button>
              <Button
                height={34}
                disabled={exportBlocked || action.pending}
                title={exportBlocked ? exportReason : undefined}
                onClick={() => {
                  void action.run(() => begin('invoices_workbook'))
                }}
              >
                Exportă Excel
              </Button>
              {output && (
                <Button
                  variant="secondary"
                  height={34}
                  onClick={() => {
                    void action.run(() => download(jobId, output))
                  }}
                >
                  Descarcă Excel
                </Button>
              )}
            </>
          )
        }
      >
        <div className="invoice-screen">
          <input
            ref={picker}
            className="invoice-screen__picker"
            type="file"
            accept=".pdf,application/pdf"
            multiple
            onChange={(event) => {
              const files = [...(event.target.files ?? [])]
              if (files.length) upload(files)
            }}
          />
          {action.problem && (
            <FailureNotice title={action.problem.title} actions={null}>
              {action.problem.title}
            </FailureNotice>
          )}
          {rejected.map((item) => (
            <FailureNotice
              key={`${item.file_name}:${item.reason}`}
              title={item.file_name}
              actions={null}
            >
              {item.reason}
            </FailureNotice>
          ))}
          {Boolean(loadError) && (
            <FailureNotice
              title={failedTitle}
              actions={
                <Button
                  variant="secondary"
                  height={30}
                  onClick={() => {
                    ctx.refresh('job', 'status', 'slots', 'identity', 'invoices')
                  }}
                >
                  Încearcă din nou
                </Button>
              }
            >
              {loadError instanceof ApiProblem ? loadError.title : 'Cererea nu poate fi procesată.'}
            </FailureNotice>
          )}
          {firstLoading && <p className="invoice-screen__loading">Se încarcă…</p>}
          {!firstLoading && view === 'empty' && (
            <EmptyState
              mark="brand"
              title="Adaugă facturile"
              actions={
                <Button
                  onClick={() => {
                    pick()
                  }}
                >
                  Alege fişiere
                </Button>
              }
              footnote="PDF · max. 100 MB"
            >
              PDF-urile furnizorului de energie electrică. Ema le citeşte şi propune clientul
              lotului o singură dată.
            </EmptyState>
          )}
          {!firstLoading && view === 'unread' && (
            <>
              {readingError && (
                <FailureNotice
                  title="Facturile nu s-au putut citi"
                  actions={
                    <Button height={30} onClick={readAgain}>
                      Încearcă din nou
                    </Button>
                  }
                >
                  {readingError}
                </FailureNotice>
              )}
              <EmaWidget
                title="Facturile nu sunt citite"
                actions={
                  <Button height={32} onClick={readAgain}>
                    Citeşte facturile
                  </Button>
                }
              >
                Ema citeşte fiecare factură şi propune clientul lotului; nimic nu intră în Excel
                până nu confirmi.
              </EmaWidget>
            </>
          )}
          {!firstLoading && view === 'reading' && (
            <Card>
              <CardHeader
                title={`Facturi ${String(year ?? '')}`}
                count={`${String(fileCount)} PDF`}
              />
              <div className="invoice-screen__reading">
                <strong>Citesc facturile</strong>
                <ProgressBar value={0} running />
                <p>Poţi pleca din ecran; lucrarea continuă.</p>
              </div>
            </Card>
          )}
          {!firstLoading && view === 'identity' && identity.data && (
            <IdentityView
              jobId={jobId}
              identity={identity.data}
              client={ctx.client.data}
              batch={batch.data}
              confirm={confirm}
              pending={action.pending}
            />
          )}
          {!firstLoading && view === 'table' && batch.data && (
            <InvoiceTable
              jobId={jobId}
              batch={batch.data}
              openId={openId}
              onOpen={(id) => {
                setOpenId(openId === id ? null : id)
              }}
              onAdd={() => {
                pick()
              }}
              onReplace={(slot) => {
                pick(slot)
              }}
              onRemove={remove}
            />
          )}
        </div>
      </Content>
      <InvoiceActivity
        view={view}
        batch={batch.data}
        identity={identity.data}
        decisions={ctx.log.data ?? []}
        output={output}
        year={year}
        onUndo={undo}
        clientFieldId={ctx.fields.data?.find((field) => field.key === 'invoice.batch_client')?.id}
      />
    </Window>
  )
}
