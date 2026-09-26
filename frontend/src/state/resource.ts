// A small cache of API reads (D4): one entry per key, previous data kept while refetching,
// `invalidate` refetches what is on screen. Evidence and file versions are immutable.

import { useEffect, useRef, useSyncExternalStore } from 'react'

export type Resource<T> = { data?: T; error?: unknown; loading: boolean }

type Entry = {
  data?: unknown
  error?: unknown
  loading: boolean
  stale: boolean
  generation: number
}

const entries = new Map<string, Entry>()
const loaders = new Map<string, () => Promise<unknown>>()
const mounted = new Map<string, number>()
const listeners = new Set<() => void>()

function emit(): void {
  for (const listener of listeners) listener()
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function fetchKey(key: string): void {
  const load = loaders.get(key)
  if (!load) return
  const previous = entries.get(key)
  const generation = (previous?.generation ?? 0) + 1
  entries.set(key, { ...previous, loading: true, stale: false, generation })
  emit()
  load().then(
    (data) => {
      if (entries.get(key)?.generation !== generation) return
      entries.set(key, { data, loading: false, stale: false, generation })
      emit()
    },
    (error: unknown) => {
      if (entries.get(key)?.generation !== generation) return
      entries.set(key, { data: previous?.data, error, loading: false, stale: false, generation })
      emit()
    },
  )
}

const IDLE: Resource<never> = { loading: true }

export function useResource<T>(key: string | null, load: () => Promise<T>): Resource<T> {
  const loader = useRef(load)
  useEffect(() => {
    loader.current = load
  })
  const entry = useSyncExternalStore(subscribe, () => (key ? entries.get(key) : undefined))
  useEffect(() => {
    if (!key) return
    loaders.set(key, () => loader.current())
    mounted.set(key, (mounted.get(key) ?? 0) + 1)
    const current = entries.get(key)
    if (!current || (current.stale && !current.loading)) fetchKey(key)
    return () => {
      mounted.set(key, (mounted.get(key) ?? 1) - 1)
    }
  }, [key])
  if (!key) return { loading: false }
  if (!entry) return IDLE
  return entry as Resource<T>
}

/** Mark keys stale and refetch those on screen. */
export function invalidate(...keys: string[]): void {
  for (const key of keys) {
    const entry = entries.get(key)
    if (!entry) continue
    entries.set(key, { ...entry, stale: true })
    if ((mounted.get(key) ?? 0) > 0) fetchKey(key)
  }
  emit()
}

export function jobKey(jobId: string, name: string): string {
  return `${jobId}/${name}`
}

export function invalidateJob(jobId: string, ...names: string[]): void {
  invalidate(...names.map((name) => jobKey(jobId, name)))
}
