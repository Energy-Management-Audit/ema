import { useEffect, useState } from 'react'

export function attachBlobUrl(
  load: () => Promise<Blob>,
  onLoaded: (url: string) => void,
  onError?: (error: unknown) => void,
): () => void {
  let cancelled = false
  let current: string | null = null
  load().then(
    (data) => {
      if (cancelled) return
      current = URL.createObjectURL(data)
      onLoaded(current)
    },
    (error: unknown) => {
      if (!cancelled) onError?.(error)
    },
  )
  return () => {
    cancelled = true
    if (current) URL.revokeObjectURL(current)
  }
}

/** Keep one object URL for a fetched image and revoke it when its owner unmounts. */
export function useBlobUrl(
  load: (() => Promise<Blob>) | null,
  onError?: (error: unknown) => void,
): string | null {
  const [result, setResult] = useState<{ load: () => Promise<Blob>; url: string } | null>(null)
  useEffect(() => {
    if (!load) return
    return attachBlobUrl(
      load,
      (url) => {
        setResult({ load, url })
      },
      onError,
    )
  }, [load, onError])
  return result?.load === load ? result.url : null
}
