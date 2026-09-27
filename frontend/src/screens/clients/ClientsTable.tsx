import type { ClientOverview } from '../../api/clients-types.ts'
import type { JobOverview } from '../../api/types.ts'
import { navigate } from '../../app/navigate.ts'
import { clientHref } from '../../app/route.ts'
import { formatNumber, rel } from '../../lib/format.ts'
import { Cell } from '../../ui/Rows.tsx'
import { Tag } from '../../ui/Chip.tsx'
import { formatCui, jobTag } from '../../clients/format.ts'

function jobsFor(id: string, overview: JobOverview[]): JobOverview[] {
  return overview
    .filter((job) => job.client_slug === id)
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
}

export function ClientsTable({
  clients,
  jobs,
  year,
}: {
  clients: ClientOverview[]
  jobs: JobOverview[]
  year: number
}) {
  return (
    <div className="clients-table" role="table" aria-label="Clienţi">
      <div className="ema-table-row clients-table__head" role="row">
        <Cell grow>CLIENT</Cell>
        <Cell width={94}>CUI</Cell>
        <Cell width={82}>JUDEŢ</Cell>
        <Cell width={153}>ACTIVITATE (CAEN)</Cell>
        <Cell width={142}>LUCRĂRI</Cell>
        <Cell width={88} figures>
          CONSUM {year}
        </Cell>
        <Cell width={118}>ULTIMA ACTIVITATE</Cell>
      </div>
      {clients.map((client) => {
        const own = jobsFor(client.id, jobs)
        const newest = own[0]
        const active = own.find((job) => !job.finalized)
        return (
          <div
            key={client.id}
            className="ema-table-row clients-table__row"
            role="row"
            tabIndex={0}
            onClick={() => {
              navigate(clientHref(client.id))
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter') navigate(clientHref(client.id))
            }}
          >
            <Cell grow>{client.name ?? '—'}</Cell>
            <Cell width={94} figures>
              {formatCui(client.cui)}
            </Cell>
            <Cell width={82}>{client.county ?? '—'}</Cell>
            <Cell width={153}>
              <span className="clients-table__caen">
                {[client.caen, client.caen_description].filter(Boolean).join(' ') || '—'}
              </span>
            </Cell>
            <Cell width={142}>
              <span className="clients-table__tags">
                {own.slice(0, 3).map((job) => (
                  <Tag key={job.id}>{jobTag(job)}</Tag>
                ))}
                {own.length === 0 && '—'}
              </span>
            </Cell>
            <Cell width={88} figures>
              {client.consumption?.year === year
                ? `${formatNumber(client.consumption.total_tep)} tep`
                : '—'}
            </Cell>
            <Cell width={118}>
              <span className="clients-table__activity">
                {own.length > 0 ? rel(newest.updated_at) : '—'}
                {active && (active.blocking ?? 0) > 0 && (
                  <small>
                    <span className="ema-dot ema-dot--warn" />
                    {active.blocking} de rezolvat
                  </small>
                )}
              </span>
            </Cell>
          </div>
        )
      })}
    </div>
  )
}
