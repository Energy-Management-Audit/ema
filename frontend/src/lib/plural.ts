/** Romanian counted nouns: 1 singular; nonzero endings 00 or 20–99 take „de”. */
export function noun(count: number, singular: string, plural: string): string {
  if (count === 1) return singular
  const ending = count % 100
  return `${count !== 0 && (ending === 0 || ending >= 20) ? 'de ' : ''}${plural}`
}

export function plural(count: number, singular: string, many: string): string {
  return `${String(count)} ${noun(count, singular, many)}`
}
