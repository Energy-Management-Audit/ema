import { api } from '../api/endpoints.ts'
import { jobHref, type Tab } from '../app/route.ts'
import { navigate } from '../app/navigate.ts'
import { blockingFooter, blockingItems } from '../piee/readiness.ts'
import { useJob } from '../state/job.tsx'
import { jobKey, useResource } from '../state/resource.ts'
import { ActivityPanel } from '../ui/Activity'
import { Status } from '../ui/Chip'
import { SectionKey } from '../ui/Surface'
import { isMeasureDecision, JournalEntries } from './JournalEntries.tsx'
import { RunPanel } from './RunPanel.tsx'

export function useMissing(jobId: string) {
  return useResource(jobKey(jobId, 'missing'), () => api.missing(jobId))
}

/** What blocks the final export (Q2 A: conflicts never block the draft). */
export function BlockingPanel() {
  const ctx = useJob()
  const missing = useMissing(ctx.jobId)
  const items = blockingItems(
    ctx.checks.data,
    ctx.fields.data ?? [],
    missing.data ?? [],
    ctx.job.data?.year ?? null,
  )
  return (
    <div className="blocking-panel" data-testid="blocking-panel">
      {items.map((item, index) => (
        <div className="blocking-item" key={`${item.fieldId ?? item.status}-${String(index)}`}>
          <div className="blocking-item__line">
            <Status tone={item.tone}>{item.status}</Status>
            <span className="blocking-item__label">{item.label}</span>
          </div>
          {item.detail && <small>{item.detail}</small>}
        </div>
      ))}
    </div>
  )
}

export function ActivityColumn({ tab }: { tab: Tab }) {
  const ctx = useJob()
  const all = () => {
    navigate(jobHref(ctx.jobId, 'jurnal'))
  }
  if (tab === 'date' || tab === 'jurnal') {
    return (
      <ActivityPanel
        title="Ce blochează exportul final"
        onAll={all}
        footer={<span className="activity-footnote">{blockingFooter(ctx.checks.data)}</span>}
      >
        <RunPanel />
        <BlockingPanel />
        {tab === 'date' && (
          <>
            <div className="activity-section">
              <SectionKey>Ce s-a întâmplat</SectionKey>
            </div>
            <JournalEntries max={10} />
          </>
        )}
      </ActivityPanel>
    )
  }
  if (tab === 'masuri') {
    const summary = ctx.summary.data
    const done = summary?.measures_complete ?? 0
    const total = summary?.measures_total ?? 0
    const width = total > 0 ? Math.round((done / total) * 100) : 0
    return (
      <ActivityPanel
        title="Ce s-a întâmplat"
        onAll={all}
        footer={
          <>
            <div className="ema-count-bar__line">
              <span className="ema-section-key">GATA DE EXPORT</span>
              <span
                className={`ema-count-bar__count ${done >= total && total > 0 ? 'is-complete' : ''}`}
              >
                {done} / {total}
              </span>
            </div>
            <span className="ema-count-bar__track">
              <span className="ema-count-bar__fill" style={{ width: `${String(width)}%` }} />
            </span>
            <span className="activity-footnote">Ce lipseşte apare marcat cu roşu în program.</span>
          </>
        }
      >
        <RunPanel />
        <JournalEntries filter={isMeasureDecision} max={20} />
      </ActivityPanel>
    )
  }
  return (
    <ActivityPanel title="Ce s-a întâmplat" onAll={all}>
      <RunPanel />
      <JournalEntries max={10} />
    </ActivityPanel>
  )
}
