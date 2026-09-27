// Browser routes stay outside the API proxy namespace.

export const TABS = ['documente', 'date', 'masuri', 'jurnal', 'predare'] as const
export const AUDIT_TABS = [
  'documente',
  'structura',
  'revizuire',
  'jurnal',
  'masuratori',
  'raport',
  'predare',
] as const
export const CLIENT_TABS = ['date', 'lucrari', 'puncte', 'memorie'] as const
export const SETTINGS_GROUPS = ['extragere', 'fisiere', 'aspect', 'despre'] as const

export type Tab = (typeof TABS)[number]
export type AuditTab = (typeof AUDIT_TABS)[number]
export type ClientTab = (typeof CLIENT_TABS)[number]
export type SettingsGroup = (typeof SETTINGS_GROUPS)[number]

export type Route =
  | { name: 'home' }
  | { name: 'clients' }
  | { name: 'client'; clientId: string; tab: ClientTab }
  | { name: 'reporting' }
  | { name: 'settings'; group: SettingsGroup }
  | { name: 'job'; jobId: string; tab: Tab; field: string | null }
  | { name: 'audit'; jobId: string; tab: AuditTab; field: string | null }
  | { name: 'invoices'; jobId: string }
  | { name: 'unknown' }

function decoded(value: string): string | null {
  try {
    return decodeURIComponent(value)
  } catch {
    return null
  }
}

export function parseRoute(pathname: string, search = ''): Route {
  const path = pathname.replace(/\/+$/, '')
  if (path === '/app' || path === '') return { name: 'home' }
  if (path === '/app/clienti') return { name: 'clients' }
  if (path === '/app/raportare') return { name: 'reporting' }
  if (path === '/app/setari') return { name: 'settings', group: 'extragere' }
  const settings = /^\/app\/setari\/([^/]+)$/.exec(path)
  if (settings?.[1]) {
    const group = SETTINGS_GROUPS.find((item) => item === settings[1])
    return group ? { name: 'settings', group } : { name: 'unknown' }
  }
  const client = /^\/app\/clienti\/([^/]+)(?:\/([^/]+))?$/.exec(path)
  if (client?.[1]) {
    const clientId = decoded(client[1])
    const tab = CLIENT_TABS.find((item) => item === (client[2] || 'date'))
    return clientId !== null && tab ? { name: 'client', clientId, tab } : { name: 'unknown' }
  }
  const invoice = /^\/app\/facturi\/([^/]+)$/.exec(path)
  if (invoice?.[1]) {
    const jobId = decoded(invoice[1])
    return jobId !== null ? { name: 'invoices', jobId } : { name: 'unknown' }
  }
  const match = /^\/app\/(piee|audit)\/([^/]+)\/([^/]+)$/.exec(path)
  if (!match?.[1] || !match[2] || !match[3]) return { name: 'unknown' }
  const jobId = decoded(match[2])
  if (jobId === null) return { name: 'unknown' }
  const field = new URLSearchParams(search).get('camp')
  if (match[1] === 'piee') {
    const tab = TABS.find((item) => item === match[3])
    return tab ? { name: 'job', jobId, tab, field } : { name: 'unknown' }
  }
  const tab = AUDIT_TABS.find((item) => item === match[3])
  return tab ? { name: 'audit', jobId, tab, field } : { name: 'unknown' }
}

export function href(route: Route): string {
  switch (route.name) {
    case 'home':
    case 'unknown':
      return '/app/'
    case 'clients':
      return '/app/clienti'
    case 'client':
      return `/app/clienti/${encodeURIComponent(route.clientId)}/${route.tab}`
    case 'reporting':
      return '/app/raportare'
    case 'settings':
      return `/app/setari/${route.group}`
    case 'invoices':
      return `/app/facturi/${encodeURIComponent(route.jobId)}`
    case 'job':
    case 'audit': {
      const base = `/app/${route.name === 'job' ? 'piee' : 'audit'}/${encodeURIComponent(route.jobId)}/${route.tab}`
      return route.field ? `${base}?camp=${encodeURIComponent(route.field)}` : base
    }
  }
}

export function jobHref(jobId: string, tab: Tab, field: string | null = null): string {
  return href({ name: 'job', jobId, tab, field })
}

export function auditHref(
  jobId: string,
  tab: AuditTab = 'documente',
  field: string | null = null,
): string {
  return href({ name: 'audit', jobId, tab, field })
}

export function invoicesHref(jobId: string): string {
  return href({ name: 'invoices', jobId })
}

export function clientHref(clientId: string, tab: ClientTab = 'date'): string {
  return href({ name: 'client', clientId, tab })
}

export function jobPath(job: { id: string; type: string }): string {
  if (job.type === 'piee') return jobHref(job.id, 'date')
  if (job.type === 'audit') return auditHref(job.id)
  if (job.type === 'invoices') return invoicesHref(job.id)
  return '/app/'
}
