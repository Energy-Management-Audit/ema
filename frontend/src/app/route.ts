// Path routes under /app/ (D1). No proxied or API path starts with /app.

export const TABS = ['documente', 'date', 'masuri', 'jurnal', 'predare'] as const
export type Tab = (typeof TABS)[number]

export type Route =
  | { name: 'home' }
  | { name: 'job'; jobId: string; tab: Tab; field: string | null }
  | { name: 'unknown' }

export function parseRoute(pathname: string, search = ''): Route {
  const path = pathname.replace(/\/+$/, '')
  if (path === '/app' || path === '') return { name: 'home' }
  const match = /^\/app\/piee\/([^/]+)\/([a-z]+)$/.exec(path)
  if (!match?.[1] || !match[2]) return { name: 'unknown' }
  const tab = TABS.find((item) => item === match[2])
  if (!tab) return { name: 'unknown' }
  const field = new URLSearchParams(search).get('camp')
  return { name: 'job', jobId: decodeURIComponent(match[1]), tab, field }
}

export function href(route: Route): string {
  if (route.name !== 'job') return '/app/'
  const base = `/app/piee/${encodeURIComponent(route.jobId)}/${route.tab}`
  return route.field ? `${base}?camp=${encodeURIComponent(route.field)}` : base
}

export function jobHref(jobId: string, tab: Tab, field: string | null = null): string {
  return href({ name: 'job', jobId, tab, field })
}
