import { useEffect, useImperativeHandle, useRef, useState, type Ref } from 'react'
import { api } from '../../api/endpoints.ts'
import { loadPdf, type PDFDocumentProxy } from '../../api/pdf.ts'

const WIDTH = 560
const AHEAD = 2

export type PdfState = {
  doc: PDFDocumentProxy | null
  pages: number
  failed: boolean
  retry: () => void
}
type Loaded = Omit<PdfState, 'retry'>

/** The PDF output of a render, fetched as bytes from its authenticated output (never an
 * <iframe> or <embed> at an API path) and parsed by pdf.js in its bundled worker. */
export function usePdfDocument(jobId: string, outputId: string | null): PdfState {
  const [state, setState] = useState<Loaded>({ doc: null, pages: 0, failed: false })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!outputId) return
    const load = { cancelled: false, destroy: null as (() => void) | null }
    const alive = () => !load.cancelled
    void (async () => {
      try {
        const bytes = new Uint8Array(await (await api.output(jobId, outputId)).arrayBuffer())
        if (!alive()) return
        const task = loadPdf(bytes)
        load.destroy = () => void task.destroy()
        const doc = await task.promise
        if (alive()) setState({ doc, pages: doc.numPages, failed: false })
      } catch {
        if (alive()) setState({ doc: null, pages: 0, failed: true })
      }
    })()
    return () => {
      load.cancelled = true
      load.destroy?.()
      setState({ doc: null, pages: 0, failed: false })
    }
  }, [jobId, outputId, attempt])
  return {
    ...state,
    retry: () => {
      setAttempt((value) => value + 1)
    },
  }
}

export type PdfPagesHandle = { scrollToPage: (index: number) => void }

/** 3d centre: every page on paper, 560 wide, rendered only when near the viewport. */
export function PdfPages({
  doc,
  pages,
  ref,
}: {
  doc: PDFDocumentProxy
  pages: number
  ref?: Ref<PdfPagesHandle>
}) {
  const frames = useRef<(HTMLDivElement | null)[]>([])
  const [ratio, setRatio] = useState(Math.SQRT2)
  const [visible, setVisible] = useState<Set<number>>(() => new Set([0]))

  useImperativeHandle(ref, () => ({
    scrollToPage(index: number) {
      frames.current[index]?.scrollIntoView({ block: 'start', behavior: 'smooth' })
    },
  }))

  useEffect(() => {
    let cancelled = false
    void doc.getPage(1).then((page) => {
      const viewport = page.getViewport({ scale: 1 })
      if (!cancelled) setRatio(viewport.height / viewport.width)
    })
    return () => {
      cancelled = true
    }
  }, [doc])

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        setVisible((current) => {
          const next = new Set(current)
          for (const entry of entries) {
            const index = Number((entry.target as HTMLElement).dataset.page)
            if (entry.isIntersecting) next.add(index)
            else next.delete(index)
          }
          return next
        })
      },
      { rootMargin: '200px 0px' },
    )
    for (const frame of frames.current) if (frame) observer.observe(frame)
    return () => {
      observer.disconnect()
    }
  }, [pages])

  const near = new Set<number>()
  for (const index of visible) {
    for (let offset = -AHEAD; offset <= AHEAD; offset++) near.add(index + offset)
  }

  return (
    <div className="report-pages" data-testid="pdf-pages" data-pages={pages}>
      {Array.from({ length: pages }, (_, index) => (
        <div
          key={index}
          ref={(node) => {
            frames.current[index] = node
          }}
          className="ema-paper report-page"
          data-page={index}
          data-testid="pdf-page"
          style={{ height: WIDTH * ratio }}
        >
          <span className="report-page__number">{index + 1}</span>
          {near.has(index) && <PageCanvas doc={doc} index={index} />}
        </div>
      ))}
    </div>
  )
}

function PageCanvas({ doc, index }: { doc: PDFDocumentProxy; index: number }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    let cancelled = false
    let cancel: (() => void) | null = null
    void doc.getPage(index + 1).then((page) => {
      const target = canvas.current
      if (cancelled || !target) return
      const scale = (WIDTH / page.getViewport({ scale: 1 }).width) * window.devicePixelRatio
      const viewport = page.getViewport({ scale })
      target.width = Math.floor(viewport.width)
      target.height = Math.floor(viewport.height)
      const task = page.render({ canvas: target, viewport })
      cancel = () => {
        task.cancel()
      }
      task.promise.catch(() => undefined)
    })
    return () => {
      cancelled = true
      cancel?.()
    }
  }, [doc, index])
  return <canvas ref={canvas} className="report-page__canvas" />
}
