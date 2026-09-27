import type { ClientOverview } from '../api/clients-types.ts'

function plain(value: string): string {
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
