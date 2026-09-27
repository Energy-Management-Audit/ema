/** Counted Romanian nouns: 1 singular; „de” for nonzero counts ending in 00 or 20–99. */
export function plural(count: number, singular: string, many: string): string {
  const number = String(count)
  if (count === 1) return `${number} ${singular}`
  const lastTwo = count % 100
  return count !== 0 && (lastTwo === 0 || lastTwo >= 20)
    ? `${number} de ${many}`
    : `${number} ${many}`
}
