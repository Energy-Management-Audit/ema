import { noun } from '../lib/plural.ts'

const WORDS = [
  'zero',
  'una',
  'două',
  'trei',
  'patru',
  'cinci',
  'şase',
  'şapte',
  'opt',
  'nouă',
  'zece',
]

export function countWords(count: number): string {
  return WORDS[count] ?? String(count)
}

export function attentionLine(count: number, blocking: number): string {
  if (count === 0) return ''
  if (blocking === 1) return 'o lucrare aşteaptă o decizie de la tine'
  if (blocking > 1)
    return `${String(blocking)} ${noun(blocking, 'lucrare', 'lucrări')} aşteaptă o decizie de la tine`
  if (count === 1) return 'lucrarea este la zi'
  return `toate cele ${countWords(count)} ${noun(count, 'lucrare', 'lucrări')} sunt la zi`
}
