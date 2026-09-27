import type { Ref } from 'react'
import { Check } from 'lucide-react'
import type { RenderSummary } from '../../api/audit-report-types.ts'
import { CHAPTERS, countRo, fieldsLine, markerLabels, unitLine } from '../../audit/report.ts'
import { Button } from '../../ui/Button'
import { Exclamation, Icon } from '../../ui/Icon'
import { SectionKey } from '../../ui/Surface'

function sectionName(sectionId: string): string {
  const chapter = /^ch(\d)$/.exec(sectionId)
  return chapter ? (CHAPTERS[Number(chapter[1]) - 1]?.title ?? sectionId) : sectionId
}

export type PanelFile = { name: string; size: string }

/** 3d „Ce intră în raport”: what went into the file, the fields still empty, and the version. */
export function ReportPanel({
  summary,
  file,
  onFill,
  onDownload,
  downloading = false,
  markersRef,
}: {
  summary: RenderSummary | null
  file: PanelFile | null
  onFill?: () => void
  onDownload?: () => void
  downloading?: boolean
  markersRef?: Ref<HTMLDivElement>
}) {
  const labels = summary ? markerLabels(summary.markers) : []
  return (
    <aside className="ema-activity report-panel" data-testid="report-panel">
      <div className="ema-activity__head">
        <span className="ema-activity__title">Ce intră în raport</span>
      </div>
      <div className="report-panel__rows">
        {summary && (
          <>
            <div className="report-panel__row">
              <span className="report-panel__line">
                <Icon icon={Check} size={12} stroke={2.6} color="var(--olive-mark)" />
                {countRo(summary.fields_confirmed, 'câmp confirmat', 'câmpuri confirmate')}
              </span>
              <span className="report-panel__detail">{fieldsLine(summary)}</span>
            </div>
            <div className="report-panel__row">
              <span className="report-panel__line">
                <Icon icon={Check} size={12} stroke={2.6} color="var(--olive-mark)" />
                {`${countRo(summary.tables, 'tabel', 'tabele')}, ${countRo(summary.charts, 'grafic', 'grafice')}`}
              </span>
              <span className="report-panel__detail">formatate după şablonul EMA</span>
            </div>
            {summary.markers.length > 0 && (
              <div
                className="report-panel__row report-panel__row--markers"
                ref={markersRef}
                tabIndex={-1}
                data-testid="report-markers"
              >
                <span className="report-panel__line">
                  <span className="report-panel__bang" aria-hidden>
                    !
                  </span>
                  {countRo(summary.markers.length, 'câmp rămas gol', 'câmpuri rămase goale')}
                </span>
                <span className="report-panel__detail">{labels.join(' · ')}</span>
                <span className="report-panel__detail">
                  apar în Word ca <span className="report-panel__marker">[de completat]</span>
                </span>
                {onFill && (
                  <Button
                    variant="secondary"
                    height={26}
                    className="report-panel__fill"
                    onClick={onFill}
                  >
                    Le completez acum
                  </Button>
                )}
              </div>
            )}
            <div className="report-panel__row">
              <span className="report-panel__line">
                <span className="report-panel__dot" aria-hidden>
                  ·
                </span>
                Unităţi repetate
              </span>
              <span className="report-panel__detail">{unitLine(summary.unit_plan)}</span>
            </div>
            {summary.failures.map((failure) => (
              <div key={failure.section_id} className="report-panel__row">
                <span className="report-panel__line report-panel__line--failed">
                  <Icon icon={Exclamation} size={12} stroke={1.9} color="var(--error-ink)" />
                  {`${sectionName(failure.section_id)} nu s-a putut scrie`}
                </span>
                <span className="report-panel__detail report-panel__code">{failure.code}</span>
              </div>
            ))}
          </>
        )}
      </div>
      {file && (
        <div className="report-panel__version">
          <SectionKey>VERSIUNEA</SectionKey>
          <div className="report-panel__file">
            <span className="report-panel__name">{file.name}</span>
            <span className="report-panel__size">{file.size}</span>
            <Button
              variant="quiet"
              height={26}
              loading={downloading}
              disabled={!onDownload || downloading}
              onClick={onDownload}
            >
              Descarcă
            </Button>
          </div>
          <span className="report-panel__note">
            Versiunea anterioară rămâne — nimic nu se suprascrie.
          </span>
        </div>
      )}
    </aside>
  )
}
