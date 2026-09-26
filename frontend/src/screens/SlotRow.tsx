import { File, Sheet } from 'lucide-react'
import { api } from '../api/endpoints.ts'
import { formatBytes } from '../lib/format.ts'
import { useJob } from '../state/job.tsx'
import { jobKey, useResource } from '../state/resource.ts'
import { Status } from '../ui/Chip'
import { Icon } from '../ui/Icon'

export const SLOT_TITLES: Record<string, string> = {
  anexa: 'Anexa 2–3',
  prelucrare: 'Prelucrare date',
  questionnaire: 'Necesar info',
  previous_piee: 'PIEE anterior',
}

export type ReadState = 'unread' | 'stale' | 'read'

function span(years: number[]): string {
  return years.length ? `${String(years[0])}–${String(years.at(-1))}` : ''
}

function detail(slot: string, jobYear: number | null, prelucrareYears: number[]): string {
  if (slot === 'anexa') {
    return `Anexa 2–3 · ${jobYear === null ? '' : String(jobYear - 1)} · identitate, date anuale, măsuri`
  }
  if (slot === 'prelucrare') {
    return `Prelucrare date · a Marianei · acoperă ${span(prelucrareYears)} · autoritară pentru aceşti ani`
  }
  return SLOT_TITLES[slot] ?? slot
}

/** One input slot of M6: the active file's name and size, what it holds, whether Ema read it. */
export function SlotRow({
  slot,
  filled,
  read,
  prelucrareYears,
}: {
  slot: string
  filled: boolean
  read: ReadState
  prelucrareYears: number[]
}) {
  const { jobId, job } = useJob()
  const versions = useResource(filled ? jobKey(jobId, `slot:${slot}`) : null, () =>
    api.slotVersions(jobId, slot),
  )
  const active = versions.data?.reduce<(typeof versions.data)[number] | null>(
    (best, item) => (best === null || item.version > best.version ? item : best),
    null,
  )
  const client = job.data?.client_slug ?? ''
  const files = useResource(active ? `fileVersions:${active.file_sha}` : null, () =>
    api.fileVersions(client, active?.file_sha ?? ''),
  )
  const file = files.data?.find((item) => item.sha === active?.file_sha)
  const glyph = slot === 'prelucrare' ? Sheet : File
  if (!filled) {
    const covered = slot === 'questionnaire' && prelucrareYears.length > 0
    return (
      <div className="slot-row slot-row--empty" data-testid={`slot-row-${slot}`}>
        <Icon icon={glyph} size={16} stroke={1.6} />
        <div className="slot-row__text">
          <span className="slot-row__name">{SLOT_TITLES[slot]}</span>
          {covered && (
            <span className="slot-row__detail">
              {`nu e nevoie: anii ${span(prelucrareYears)} sunt acoperiţi de Prelucrare date`}
            </span>
          )}
        </div>
        {slot === 'anexa' ? (
          <Status tone="warn">lipseşte</Status>
        ) : (
          <Status tone="muted">neobligatoriu</Status>
        )}
        <span />
      </div>
    )
  }
  return (
    <div className="slot-row" data-testid={`slot-row-${slot}`}>
      <Icon icon={glyph} size={16} stroke={1.6} />
      <div className="slot-row__text">
        <span className="slot-row__name slot-row__name--file">
          {file?.name ?? SLOT_TITLES[slot]}
        </span>
        <span className="slot-row__detail">
          {detail(slot, job.data?.year ?? null, prelucrareYears)}
        </span>
      </div>
      {read === 'unread' ? (
        <Status tone="muted">necitită</Status>
      ) : read === 'stale' ? (
        <Status tone="warn">citeşte din nou</Status>
      ) : (
        <Status tone="ok">citită</Status>
      )}
      <span className="slot-row__size">{file ? formatBytes(file.size_bytes) : ''}</span>
    </div>
  )
}
