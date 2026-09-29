import { plural as romanianCount, noun as romanianForm } from '../../lib/plural.ts'
import { Check } from 'lucide-react'
import { api } from '../../api/endpoints.ts'
import type { InvoiceBatchView, InvoiceIdentity } from '../../api/invoices-types.ts'
import type { Client } from '../../api/types.ts'
import { clientHref } from '../../app/route.ts'
import { navigate } from '../../app/navigate.ts'
import { jobKey, useResource } from '../../state/resource.ts'
import { Button } from '../../ui/Button.tsx'
import { FailureNotice } from '../../ui/Feedback.tsx'
import { Highlight } from '../../ui/Review.tsx'
import { BrandMark, GroupBox, Paper, SectionKey } from '../../ui/Surface.tsx'
import { statusSingular, statusWord } from '../../invoices/labels.ts'

function digits(value: string | null | undefined): string {
  return value?.replace(/\D/g, '') ?? ''
}

function IdentitySnippet({ jobId, evidenceId }: { jobId: string; evidenceId: string }) {
  const evidence = useResource(`evidence/${evidenceId}`, () => api.evidence(evidenceId))
  const source = useResource(jobKey(jobId, `identity-source-${evidenceId}`), async () => {
    const item = await api.evidence(evidenceId)
    const slots = await api.slots(jobId)
    const versions = await Promise.all(
      slots
        .filter((slot) => slot.startsWith('invoices/'))
        .map((slot) => api.slotVersions(jobId, slot)),
    )
    return versions.flat().find((version) => version.file_sha === item.file_sha)?.origin ?? 'PDF'
  })
  const quote = evidence.data?.quote ?? ''
  const name = evidence.data?.quote?.match(/Client[^:]*:\s*([^\n]+)/i)?.[1]
  const page =
    evidence.data?.locator && 'page' in evidence.data.locator
      ? String(evidence.data.locator.page)
      : '—'
  return (
    <Paper className="invoice-identity__paper">
      <span className="invoice-identity__source">
        {source.data ?? 'PDF'} · pag. {page}
      </span>
      <strong>Client</strong>
      <span>
        {name && quote.includes(name) ? (
          <>
            {quote.slice(0, quote.indexOf(name))}
            <Highlight>{name}</Highlight>
            {quote.slice(quote.indexOf(name) + name.length)}
          </>
        ) : (
          quote
        )}
      </span>
    </Paper>
  )
}

export function OtherFiles({ files }: { files: InvoiceBatchView['files'] }) {
  if (!files.length) return null
  const grouped = new Map<string, { status: string; reason: string; count: number }>()
  for (const file of files) {
    const key = `${file.status}\u0000${file.reason ?? ''}`
    const item = grouped.get(key)
    if (item) item.count += 1
    else grouped.set(key, { status: file.status, reason: file.reason ?? '', count: 1 })
  }
  return (
    <section className="invoice-identity__other">
      <SectionKey>CE SE ÎNTÂMPLĂ CU CELELALTE FIŞIERE</SectionKey>
      <GroupBox>
        {[...grouped.values()].map((item) => (
          <div className="invoice-identity__other-row" key={`${item.status}:${item.reason}`}>
            <span>
              {romanianCount(item.count, statusSingular(item.status), statusWord(item.status))}
            </span>
            <p>{item.reason}</p>
          </div>
        ))}
      </GroupBox>
    </section>
  )
}

export function PodFillBox({ fills }: { fills: InvoiceIdentity['pod_fill'] }) {
  if (!fills.length) return null
  const files = fills.flatMap((item) => item.files)
  return (
    <div className="invoice-identity__pod">
      <strong>
        POD-ul se completează la {romanianCount(files.length, 'factură', 'facturi')} care nu îl
        {files.length === 1 ? 'tipăreşte' : 'tipăresc'}
      </strong>
      <span>
        {files.join(', ')} — POD-ul unic din celelalte {fills[0]?.source_count ?? 0} facturi, cu
        confirmarea ta ca dovadă. Dacă lotul ar avea mai multe POD-uri, nu s-ar completa nimic.
      </span>
    </div>
  )
}

export function IdentityCard({
  jobId,
  identity,
  client,
  batch,
  confirm,
  pending,
}: {
  jobId: string
  identity: InvoiceIdentity
  client: Client | undefined
  batch: InvoiceBatchView | undefined
  confirm: () => void
  pending: boolean
}) {
  const candidateCui = digits(identity.candidate?.cui)
  const clientCui = digits(identity.client_cui)
  const mismatch = Boolean(candidateCui && clientCui && candidateCui !== clientCui)
  if (!identity.candidate) {
    return (
      <FailureNotice title="Ema nu a găsit clientul pe facturi" actions={null}>
        Nicio factură nu tipăreşte un client recunoscut. Verifică fişierele de mai jos.
      </FailureNotice>
    )
  }
  return (
    <>
      {mismatch && (
        <FailureNotice
          title="Facturile par ale altui client"
          actions={
            <Button
              variant="secondary"
              height={30}
              onClick={() => {
                navigate(clientHref(identity.candidate?.client_id ?? '', 'lucrari'))
              }}
            >
              Deschide clientul
            </Button>
          }
        >
          Pe facturi apare {identity.name} (CUI {identity.candidate.cui}), dar lucrarea e a
          clientului {client?.name ?? ''} (CUI {identity.client_cui}).
        </FailureNotice>
      )}
      <div className="invoice-identity__card">
        <div className="invoice-identity__top">
          <BrandMark size={30} />
          <div>
            <strong>{identity.name}</strong>
            <span>CUI {identity.candidate.cui ?? '—'}</span>
          </div>
          {!mismatch && (
            <Button
              variant="olive"
              height={34}
              icon={Check}
              loading={pending}
              disabled={pending}
              onClick={confirm}
            >
              Confirmă clientul
            </Button>
          )}
        </div>
        <div className="invoice-identity__evidence">
          <div>
            <SectionKey>DE CE ACEST CLIENT</SectionKey>
            <p>
              <b>{identity.reasons.printed}</b>{' '}
              {romanianForm(identity.reasons.printed, 'factură', 'facturi')} îl{' '}
              {identity.reasons.printed === 1 ? 'tipăreşte' : 'tipăresc'} ca „Client”
            </p>
            {identity.reasons.pods.length === 1 && (
              <p>
                <b>1</b> POD distinct în facturile cu POD: {identity.reasons.pods[0]}
              </p>
            )}
            {identity.reasons.pods.length > 1 && (
              <p>
                <b>{identity.reasons.pods.length}</b> POD-uri distincte în facturile cu POD
              </p>
            )}
            <p>
              <b>{identity.reasons.other_client}</b>{' '}
              {romanianForm(identity.reasons.other_client, 'factură', 'facturi')} cu alt client
            </p>
          </div>
          {identity.evidence_ids[0] && (
            <IdentitySnippet jobId={jobId} evidenceId={identity.evidence_ids[0]} />
          )}
        </div>
        <PodFillBox fills={identity.pod_fill} />
      </div>
      <OtherFiles files={batch?.files ?? []} />
    </>
  )
}

export function IdentityView(props: Parameters<typeof IdentityCard>[0]) {
  return (
    <div className="invoice-identity">
      <IdentityCard {...props} />
    </div>
  )
}
