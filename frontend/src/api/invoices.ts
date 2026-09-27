import { blob, request } from './client.ts'
import type { InvoiceBatchView, InvoiceIdentity, InvoiceUpload } from './invoices-types.ts'

const root = (id: string) => `/jobs/${encodeURIComponent(id)}/invoices`

export const invoicesApi = {
  batch: (id: string) => request<InvoiceBatchView>('GET', root(id)),
  identity: (id: string) => request<InvoiceIdentity>('GET', `${root(id)}/identity`),
  confirm: (id: string, clientId: string, revision: number) =>
    request<InvoiceIdentity>('POST', `${root(id)}/identity`, {
      client_id: clientId,
      on_revision: revision,
      confirm: true,
    }),
  uploadInvoices: (id: string, files: File[], replace?: string) => {
    const form = new FormData()
    for (const file of files) form.append('files', file)
    const query = replace ? `?replace=${encodeURIComponent(replace)}` : ''
    return request<InvoiceUpload>('POST', `${root(id)}/files${query}`, form)
  },
  pagePng: (id: string, slot: string, page: number, crop = false) =>
    blob(
      `${root(id)}/page.png?slot=${encodeURIComponent(slot)}&page=${String(page)}${crop ? '&crop=active_energy' : ''}`,
    ),
  invoicePdf: (id: string, slot: string) =>
    blob(`${root(id)}/file?slot=${encodeURIComponent(slot)}`),
}
