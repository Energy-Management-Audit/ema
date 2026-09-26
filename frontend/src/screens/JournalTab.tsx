import { useJob } from '../state/job.tsx'
import { JournalEntries } from './JournalEntries.tsx'

/** S5: the whole decision log at content width, newest first. */
export function JournalTab() {
  const { log } = useJob()
  if (!log.data) return <p className="app-loading">Se încarcă…</p>
  if (log.data.length === 0) return <p className="app-loading">Nicio decizie încă.</p>
  return (
    <div className="journal">
      <JournalEntries />
    </div>
  )
}
