import { GlobalWorkerOptions, VerbosityLevel, getDocument } from 'pdfjs-dist'
import worker from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

export type { PDFDocumentProxy } from 'pdfjs-dist'

// The worker is a same-origin asset of the build: the preview never reaches the network.
GlobalWorkerOptions.workerSrc = worker

/** Load only bytes fetched from an authenticated output; never pass an input URL. pdf.js stays
 * silent (errors only), so the app's console stays clean. */
export function loadPdf(data: Uint8Array<ArrayBuffer>) {
  return getDocument({ data, verbosity: VerbosityLevel.ERRORS })
}
