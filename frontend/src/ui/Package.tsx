import type { ReactNode } from 'react'
import { Check, File, FileSpreadsheet, FileText } from 'lucide-react'
import { Exclamation, Icon } from './Icon'
import './package.css'

/** A pre-export check "7a": the mark (ok, warn, err), the statement and its mono figure. */
export function ExportCheck({
  tone,
  label,
  detail,
  testId,
}: {
  tone: 'ok' | 'warn' | 'err'
  label: ReactNode
  detail: ReactNode
  testId?: string
}) {
  return (
    <div
      className={`ema-export-check ema-export-check--${tone}`}
      data-testid={testId}
      data-tone={tone}
    >
      {tone === 'ok' ? (
        <Icon icon={Check} size={14} stroke={2.4} color="var(--olive-mark)" />
      ) : tone === 'warn' ? (
        <span className="ema-dot ema-dot--warn" aria-hidden />
      ) : (
        <Icon icon={Exclamation} size={14} stroke={1.9} color="var(--error-ink)" />
      )}
      <span className="ema-export-check__label">{label}</span>
      <span className="ema-export-check__detail">{detail}</span>
    </div>
  )
}

const kinds = { docx: FileText, xlsx: FileSpreadsheet, pdf: File }

/** A file of the package "7a": what is delivered, with its real size. */
export function PackageFile({
  name,
  size,
  kind,
  testId,
}: {
  name: ReactNode
  size: ReactNode
  kind: 'docx' | 'xlsx' | 'pdf'
  testId?: string
}) {
  return (
    <div className="ema-package-file" data-testid={testId}>
      <Icon icon={kinds[kind]} size={15} stroke={1.6} />
      <span className="ema-package-file__name">{name}</span>
      <span className="ema-package-file__size">{size}</span>
    </div>
  )
}

/** Document thumbnail "7a": a schematic first page on paper, which never inverts. */
export function DocThumb({
  title,
  lines,
  meta,
}: {
  title: ReactNode
  lines: ReactNode
  meta: ReactNode
}) {
  return (
    <div className="ema-doc-thumb">
      <div className="ema-paper ema-doc-thumb__page">
        <span className="ema-doc-thumb__title">{title}</span>
        <span className="ema-doc-thumb__bar" style={{ width: '62%' }} />
        {[92, 84, 88].map((width) => (
          <span
            key={width}
            className="ema-doc-thumb__line"
            style={{ width: `${String(width)}%` }}
          />
        ))}
        <div className="ema-doc-thumb__table">
          <span className="ema-doc-thumb__key">TABEL · MĂSURI</span>
          {[90, 76, 83].map((width) => (
            <span
              key={width}
              className="ema-doc-thumb__line"
              style={{ width: `${String(width)}%` }}
            />
          ))}
        </div>
        {[80, 58].map((width) => (
          <span
            key={width}
            className="ema-doc-thumb__line"
            style={{ width: `${String(width)}%` }}
          />
        ))}
        <span className="ema-doc-thumb__lines">{lines}</span>
      </div>
      <span className="ema-doc-thumb__meta">{meta}</span>
    </div>
  )
}
