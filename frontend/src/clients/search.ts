import type { ClientOverview } from '../api/clients-types.ts'

export function plain(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('ro')
}

export function matchesClient(client: ClientOverview, query: string): boolean {
  const text = query.trim()
  if (!text) return true
  if (plain(client.name ?? '').includes(plain(text))) return true
  const digits = text.replace(/\D/g, '')
  if (digits.length >= 3 && (client.cui ?? '').replace(/\D/g, '').includes(digits)) return true
  return (
    text.length >= 6 && client.pods.some((pod) => pod.toLowerCase().includes(text.toLowerCase()))
  )
}

/** What the pure helpers below need of a client: a `Client` or a `ClientOverview` both fit. */
export type NamedClient = { id: string; name?: string | null; cui?: string | null }

export const clientLabel = (client: NamedClient) => client.name ?? client.id

/** The clients offered under the "Lucrare nouă" field: the name contains the text, or the CUI
 * digits contain three or more typed digits. Sorted by name. */
export function clientMatches<T extends NamedClient>(clients: T[], query: string): T[] {
  const text = plain(query.trim())
  const digits = query.replace(/\D/g, '')
  return clients
    .filter(
      (client) =>
        plain(client.name ?? '').includes(text) ||
        (digits.length >= 3 && (client.cui ?? '').replace(/\D/g, '').includes(digits)),
    )
    .sort((a, b) => clientLabel(a).localeCompare(clientLabel(b), 'ro'))
}

/** Whether the list ends with the row that adds the typed text as a new client: only for a text
 * with at least one letter that is no existing client's name (case and diacritics ignored). */
export function offersNewClient(clients: NamedClient[], query: string): boolean {
  const text = plain(query.trim())
  return (
    /\p{L}/u.test(text) && !clients.some((client) => plain((client.name ?? '').trim()) === text)
  )
}

/** The existing client that a new one would duplicate: the same name or the same CUI digits. */
export function existingClient<T extends NamedClient>(
  clients: T[],
  name: string,
  cui: string,
): T | undefined {
  const text = plain(name.trim())
  const digits = cui.replace(/\D/g, '')
  return clients.find(
    (client) =>
      (text !== '' && plain((client.name ?? '').trim()) === text) ||
      (digits !== '' && (client.cui ?? '').replace(/\D/g, '') === digits),
  )
}
