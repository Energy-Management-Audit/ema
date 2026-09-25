import { createLucideIcon, type LucideIcon } from 'lucide-react'

/** The bare exclamation mark of the 7b failure (Lucide's circle-alert without the circle). */
export const Exclamation = createLucideIcon('exclamation', [
  ['path', { d: 'M12 8v5', key: 'stem' }],
  ['path', { d: 'M12 17h.01', key: 'dot' }],
])

/** Lucide line icons at the handoff's sizes: 13 tags, 14 small buttons, 16 navigation,
 * 17 state indicators, 20 panel titles; stroke 1.6–1.8, heavier only for check marks. */
export type IconSize = 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 20

export function Icon({
  icon: Glyph,
  size = 16,
  stroke = 1.7,
  color,
  className,
}: {
  icon: LucideIcon
  size?: IconSize
  stroke?: number
  color?: string
  className?: string
}) {
  return (
    <Glyph
      aria-hidden
      size={size}
      strokeWidth={stroke}
      color={color ?? 'currentColor'}
      className={className}
      style={{ flex: 'none' }}
    />
  )
}
