import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Check, type LucideIcon } from 'lucide-react'
import { Icon } from './Icon'
import './button.css'

export type ButtonVariant =
  'primary' | 'secondary' | 'tertiary' | 'destructive' | 'olive' | 'soft' | 'quiet'

/** Pill heights used across the handoff: 38 page actions, 36 dialogs, 34 page header,
 * 32 in rows and the Ema widget, 30/28 inline, 26 in the activity panel. */
export type ButtonHeight = 38 | 36 | 34 | 32 | 30 | 28 | 26

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant
  height?: ButtonHeight
  loading?: boolean
  icon?: LucideIcon
  iconAfter?: LucideIcon
  children: ReactNode
}

/** Button "7d": primar, secundar, terţiar, distructiv, plus the olive accept and the soft
 * undo pill from 3c. States: hover, active, loading, disabled, focus ring. */
export function Button({
  variant = 'primary',
  height = 38,
  loading = false,
  icon,
  iconAfter,
  className,
  children,
  ...rest
}: Props) {
  const iconSize = icon === Check || height < 32 ? 13 : 14
  return (
    <button
      type="button"
      className={`ema-btn ema-btn--${variant} ema-btn--h${String(height)} ${className ?? ''}`}
      aria-busy={loading || undefined}
      data-loading={loading || undefined}
      {...rest}
    >
      {icon && <Icon icon={icon} size={iconSize} stroke={icon === Check ? 2.6 : 1.7} />}
      {children}
      {iconAfter && <Icon icon={iconAfter} size={12} stroke={1.8} />}
    </button>
  )
}

/** Round icon button "7d" (the ✕ in the button row) and the quiet chrome buttons of the shell. */
export function IconButton({
  icon,
  label,
  size = 32,
  iconSize = 14,
  bordered = true,
  className,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  icon: LucideIcon
  label: string
  size?: 26 | 28 | 30 | 32
  iconSize?: 14 | 15 | 16
  bordered?: boolean
}) {
  return (
    <button
      type="button"
      aria-label={label}
      className={`ema-icon-btn ${bordered ? 'ema-icon-btn--bordered' : ''} ${className ?? ''}`}
      style={{ width: size, height: size }}
      {...rest}
    >
      <Icon icon={icon} size={iconSize} stroke={bordered ? 2 : 1.6} />
    </button>
  )
}
