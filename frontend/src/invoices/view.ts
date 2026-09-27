import type { RunRecord } from '../api/types.ts'

export type InvoiceView = 'empty' | 'reading' | 'unread' | 'identity' | 'table'

export function invoiceView(input: {
  slots: string[]
  runs: RunRecord[]
  confirmed: boolean | null
}): InvoiceView {
  if (!input.slots.some((slot) => /^invoices\/\d{4}$/.test(slot))) return 'empty'
  if (input.runs.some((run) => run.stage === 'invoices' && run.state === 'running')) {
    return 'reading'
  }
  if (
    !input.runs.some(
      (run) => run.stage === 'invoices' && run.state === 'ready' && run.publication === 'current',
    )
  ) {
    return 'unread'
  }
  return input.confirmed ? 'table' : 'identity'
}
