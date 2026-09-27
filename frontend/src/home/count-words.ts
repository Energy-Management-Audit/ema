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
  if (blocking > 1) return `${String(blocking)} lucrări aşteaptă o decizie de la tine`
  return `toate cele ${countWords(count)} lucrări sunt la zi`
}
