import type { OutlineNode } from '../api/audit-types.ts'
import { plural } from '../lib/plural.ts'

export function displayTitle(title: string): string {
  return /[a-zăâîşţ]/.test(title)
    ? title
    : title.charAt(0) + title.slice(1).toLocaleLowerCase('ro-RO')
}

export function holding(node: OutlineNode): string | null {
  const title = displayTitle(node.title)
  if (node.status === 'done' || node.status === 'n/a') return null
  if (node.status === 'later') {
    const reason =
      {
        visit: 'vizita în teren',
        thermography: 'termografia',
        electrical: 'măsurătorile electrice',
        map: 'harta',
      }[node.reason ?? ''] ??
      node.reason ??
      'datele aşteptate'
    return `${title} aşteaptă ${reason}.`
  }
  if (node.stale)
    return `${title}: ciorna e veche, s-a schimbat ${node.changed_input ?? 'o sursă'}.`
  if (node.status === 'n/a proposed')
    return `Ema propune „nu se aplică”: ${node.reason ?? node.applicability_reason ?? ''}`
  if (node.status === 'ready') return `${title}: datele sunt gata; ciorna se scrie cu agentul.`
  if (node.status === 'drafted') return `${title}: ciorna aşteaptă confirmarea ta.`
  return `${title}: lipsesc ${node.missing_facts.join(', ') || 'datele necesare'}.`
}

export function sectionStateLabel(status: string, reason?: string | null, stale = false): string {
  if (stale) return 'ciornă veche'
  if (status === 'done') return 'gata'
  if (status === 'drafted') return 'ciornă gata'
  if (status === 'ready') return 'datele sunt gata'
  if (status === 'n/a') return 'nu se aplică'
  if (status === 'n/a proposed') return 'nu se aplică · propus'
  if (status === 'later') {
    const label =
      { visit: 'vizită', thermography: 'termografie', electrical: 'măsurători', map: 'hartă' }[
        reason ?? ''
      ] ??
      reason ??
      ''
    return label ? `mai târziu · ${label}` : 'mai târziu'
  }
  return 'lipseşte'
}

export function nodeState(node: OutlineNode): string {
  return sectionStateLabel(node.status, node.reason, node.stale)
}

export function aggregate(children: OutlineNode[]): string {
  const applicable = children.filter((node) => node.status !== 'n/a')
  if (!applicable.length) return 'nu se aplică'
  if (applicable.every((node) => node.status === 'done')) return 'gata'
  if (applicable.some((node) => node.stale)) return 'ciornă veche'
  const written = applicable.filter((node) => ['drafted', 'done'].includes(node.status)).length
  if (written === applicable.length)
    return `ciornă gata · ${String(written)} din ${plural(applicable.length, 'secţiune', 'secţiuni')}`
  const later = applicable.find((node) => node.status === 'later')
  if (later)
    return `aşteaptă ${({ visit: 'vizita în teren', thermography: 'termografia', electrical: 'măsurătorile electrice', map: 'harta' } as Record<string, string>)[later.reason ?? ''] ?? 'date'}`
  return `${String(written)} din ${plural(applicable.length, 'secţiune scrisă', 'secţiuni scrise')}`
}

export function countdown(deadline: string, today = new Date()): string {
  const days = Math.ceil((new Date(`${deadline}T12:00:00`).getTime() - today.getTime()) / 86400000)
  if (days < 0) return 'termenul a trecut'
  return `mai sunt ${plural(Math.floor(days / 7), 'săptămână', 'săptămâni')} şi ${plural(days % 7, 'zi', 'zile')}`
}
