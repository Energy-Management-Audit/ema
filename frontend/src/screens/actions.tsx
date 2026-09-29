import { useCallback, useState } from 'react'
import { ApiProblem } from '../api/client.ts'
import { api } from '../api/endpoints.ts'
import type { ExportResponse, Output } from '../api/types.ts'
import { chooseExportFolder, desktopApi } from '../lib/desktop.ts'
import { FailureNotice } from '../ui/Feedback'

/** Problems that mean the page is out of date: refetch what it shows, never retry (D4). */
export const STALE_CODES = new Set([
  'stale_revision',
  'hash_mismatch',
  'output_stale',
  'output_missing',
  'not_ready',
  'job_running',
  'import_required',
])

function asProblem(error: unknown): ApiProblem {
  return error instanceof ApiProblem
    ? error
    : new ApiProblem('request_error', 0, 'Cererea nu poate fi procesată.')
}

/** One user action: pending while it runs, its problem shown where it was taken. */
export function useAction() {
  const [pending, setPending] = useState(false)
  const [problem, setProblem] = useState<ApiProblem | null>(null)
  const run = useCallback(
    async (action: () => Promise<unknown>, onProblem?: (problem: ApiProblem) => void) => {
      setPending(true)
      setProblem(null)
      try {
        await action()
        return true
      } catch (error) {
        const found = asProblem(error)
        setProblem(found)
        onProblem?.(found)
        return false
      } finally {
        setPending(false)
      }
    },
    [],
  )
  const clear = useCallback(() => {
    setProblem(null)
  }, [])
  return { pending, problem, run, clear }
}

export function ProblemNotice({ problem, body }: { problem: ApiProblem | null; body?: string }) {
  if (!problem) return null
  return (
    <FailureNotice title={problem.title} actions={null}>
      {body ?? ''}
    </FailureNotice>
  )
}

/** D3: binary content only through blob URLs; a download revokes its URL at once. */
export async function download(jobId: string, output: Output): Promise<void> {
  const bridge = desktopApi()
  if (bridge) {
    try {
      const result = await bridge.save_output(jobId, output.id)
      if (!result.ok) throw new ApiProblem(result.code, 0, result.message)
    } catch (error) {
      if (error instanceof ApiProblem) throw error
      throw new ApiProblem('desktop_save_failed', 0, 'Fişierul nu s-a putut salva.')
    }
    return
  }
  const url = URL.createObjectURL(await api.output(jobId, output.id))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = output.name
  anchor.click()
  URL.revokeObjectURL(url)
}

/** The PDF preview opens in a new tab from a blob URL, revoked after a minute. */
export async function openPreview(jobId: string, output: Output): Promise<void> {
  const bridge = desktopApi()
  if (bridge) {
    try {
      const result = await bridge.open_output(jobId, output.id)
      if (!result.ok) throw new ApiProblem(result.code, 0, result.message)
    } catch (error) {
      if (error instanceof ApiProblem) throw error
      throw new ApiProblem('desktop_open_failed', 0, 'Fişierul nu s-a putut deschide.')
    }
    return
  }
  const url = URL.createObjectURL(await api.output(jobId, output.id))
  window.open(url, '_blank')
  window.setTimeout(() => {
    URL.revokeObjectURL(url)
  }, 60_000)
}

export type ExportReceipt = { outputId: string; hash: string; response: ExportResponse }

/** Both Predare screens approve and copy through the same API flow. */
export async function exportPackage(
  jobId: string,
  outputId: string,
  hash: string,
): Promise<ExportReceipt | null> {
  const chosen = await chooseExportFolder()
  if (!chosen) return null
  const response = await api.exportFinal(jobId, outputId, hash, chosen.path)
  return { outputId, hash, response }
}
