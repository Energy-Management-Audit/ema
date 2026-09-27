/** Romanian counted nouns use singular at 1 and "de" for positive hundreds or endings 20–99. */
export function roCount(count: number, singular: string, plural: string): string {
  const ending = count % 100
  return `${String(count)}${count > 1 && (ending === 0 || ending >= 20) ? ' de ' : ' '}${count === 1 ? singular : plural}`
}
