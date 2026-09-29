import { formatDate } from '../lib/format.ts'
import type { Evidence } from '../api/types.ts'
import { plural } from '../lib/plural.ts'

export function sourceLabel(evidence: Evidence, fileName?: string): string {
  const locator = evidence.locator
  if (locator?.kind === 'pdf_region' || locator?.kind === 'pdf_text') {
    return `${fileName ?? 'Document'} · pag. ${String('page' in locator ? locator.page : '')}`
  }
  if (locator?.kind === 'cell')
    return `${fileName ?? 'Document'} · ${locator.sheet ?? ''}!${locator.ref ?? ''}`
  if (locator?.kind === 'url' && 'url' in locator) {
    let hostname = 'pagină web'
    try {
      const parsed = new URL(String(locator.url))
      if (parsed.protocol === 'https:' || parsed.protocol === 'http:')
        hostname = parsed.hostname.replace(/^www\./, '')
    } catch {
      /* An invalid source stays visible without a navigable link. */
    }
    const date = formatDate(evidence.retrieved_at)
    return `${hostname} · ${date}`
  }
  if (evidence.provenance === 'calculated')
    return `calculat · ${plural(evidence.derivation?.inputs.length ?? 0, 'intrare', 'intrări')}`
  if (locator?.kind === 'photo') return `Fotografie · ${fileName ?? 'document'}`
  return 'introdus manual'
}
