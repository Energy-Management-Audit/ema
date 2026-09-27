import type { ClientProfile } from '../../api/clients-types.ts'
import { formatCui } from '../../clients/format.ts'
import { formatDate } from '../../lib/format.ts'
import { SourceChip, Status } from '../../ui/Chip.tsx'
import { Card, SectionKey } from '../../ui/Surface.tsx'

export function IdentificationCard({ profile }: { profile: ClientProfile }) {
  const item = profile.identification
  const source =
    item?.source === 'anaf'
      ? `ANAF · ${item.retrieved_at ? formatDate(item.retrieved_at) : ''}`
      : `Anexa 2–3 · ${String(item?.annex_year ?? '')}`
  const rows: [string, string][] = [
    ['Denumire', item?.name ?? profile.client.name ?? '—'],
    ['CUI', formatCui(profile.client.cui, profile.fiscal?.vat_payer ?? false)],
    ['Nr. Registrul Comerţului', item?.registration ?? '—'],
    ['Sediu', item?.address ?? '—'],
    ['CAEN', [item?.caen, item?.caen_description].filter(Boolean).join(' — ') || '—'],
  ]
  return (
    <section className="client-section">
      <SectionKey>
        {item?.source === 'anaf'
          ? 'IDENTIFICARE · DIN ANAF'
          : item?.source === 'annex'
            ? `IDENTIFICARE · DIN ANEXA 2–3 ${String(item.annex_year)}`
            : 'IDENTIFICARE'}
      </SectionKey>
      {!item && <p>Nu există încă date ANAF sau o anexă pentru acest client.</p>}
      <Card>
        <div className="client-identification">
          {rows.map(([label, value]) => (
            <div key={label} className="client-identification__row">
              <span>{label}</span>
              <strong
                className={
                  label === 'CUI' || label === 'Nr. Registrul Comerţului' ? 'ema-figures' : ''
                }
              >
                {value}
              </strong>
              {label === 'Denumire' && item && (
                <SourceChip kind={item.source === 'anaf' ? 'online' : 'document'}>
                  {source}
                </SourceChip>
              )}
            </div>
          ))}
          {profile.fiscal && (
            <div className="client-identification__row">
              <span>Stare fiscală</span>
              <Status tone={profile.fiscal.active === false ? 'err' : 'ok'}>
                {profile.fiscal.active === null ? '—' : profile.fiscal.active ? 'activ' : 'inactiv'}
                {profile.fiscal.vat_payer ? ' · plătitor TVA' : ''}
              </Status>
            </div>
          )}
          {item?.source === 'annex' && item.cui !== profile.client.cui && (
            <div className="client-identification__row">
              <span>CUI în anexă</span>
              <strong>{item.cui}</strong>
              <SourceChip kind="document">{source}</SourceChip>
            </div>
          )}
        </div>
      </Card>
    </section>
  )
}

export function ContactCard({
  title,
  name,
  missing,
  source,
  detail,
  onComplete,
}: {
  title: string
  name?: string | null
  missing: string
  source?: string
  detail?: string
  onComplete: () => void
}) {
  return (
    <Card>
      <div className="client-contact">
        <SectionKey>{title}</SectionKey>
        {name ? (
          <>
            <strong>{name}</strong>
            {detail && <small>{detail}</small>}
            {source && <SourceChip kind="document">{source}</SourceChip>}
          </>
        ) : (
          <div className="client-contact__missing">
            <strong>lipseşte</strong>
            <span>{missing}</span>
            <button type="button" onClick={onComplete}>
              Completează
            </button>
          </div>
        )}
      </div>
    </Card>
  )
}
