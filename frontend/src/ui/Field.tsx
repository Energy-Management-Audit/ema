import type { InputHTMLAttributes, ReactNode, Ref, SelectHTMLAttributes } from 'react'
import { ChevronDown } from 'lucide-react'
import { Icon } from './Icon'
import './field.css'

/** Text field "7d" (CÂMPURI). Paper in both themes; `figures` sets Geist Mono for values with
 * units. Focus: 1.5px olive border and the soft olive ring. */
export function TextField({
  figures = false,
  width,
  className,
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & {
  figures?: boolean
  width?: number
  ref?: Ref<HTMLInputElement>
}) {
  return (
    <input
      className={`ema-field ${figures ? 'ema-field--figures' : ''} ${className ?? ''}`}
      style={{ width }}
      {...rest}
    />
  )
}

/** Missing value "7d" (necompletat): dashed amber, 1px at 60 %. */
export function MissingField({
  width = 200,
  children,
  onClick,
}: {
  width?: number
  children: ReactNode
  onClick?: () => void
}) {
  return (
    <button type="button" className="ema-field-missing" style={{ width }} onClick={onClick}>
      {children}
    </button>
  )
}

/** Select "7d" (Sursă de finanţare): native select, the handoff's chevron. */
export function Select({
  placeholder,
  children,
  className,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & { placeholder: string }) {
  return (
    <span className={`ema-select ${className ?? ''}`}>
      <select defaultValue="" {...rest}>
        <option value="" disabled>
          {placeholder}
        </option>
        {children}
      </select>
      <Icon icon={ChevronDown} size={14} stroke={1.8} className="ema-select__chevron" />
    </span>
  )
}

/** API key input "3i": the empty key, a sunken mono field beside its „Adaugă” button. */
export function KeyInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input className="ema-key-input" autoComplete="off" spellCheck={false} {...props} />
}

/** Toggle "3i": 40×23, 19px knob; on is olive, knob right. */
export function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean
  onChange: (next: boolean) => void
  label: string
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      className="ema-toggle"
      onClick={() => {
        onChange(!checked)
      }}
    >
      <span className="ema-toggle__knob" />
    </button>
  )
}
