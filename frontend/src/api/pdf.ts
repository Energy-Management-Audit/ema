import { getDocument } from 'pdfjs-dist'

/** Load only bytes fetched from an authenticated output; never pass an input URL. */
export function loadPdf(data: Uint8Array<ArrayBuffer>) {
  return getDocument({ data })
}
