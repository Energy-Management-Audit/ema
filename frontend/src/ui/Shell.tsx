import type { ReactNode } from 'react'
import { Check, PanelLeft, Plus, Search, Settings, type LucideIcon } from 'lucide-react'
import { IconButton } from './Button'
import { Icon } from './Icon'
import { BrandMark } from './Surface'
import './shell.css'

/** Window "3c": r18, hairline, window shadow. Two columns (sidebar 230 + content) or three
 * (+ activity panel 290). The columns are fixed and the content column takes the rest, so the
 * window resizes from 1280×800 up without redesign. */
export function Window({
  children,
  activity = false,
  height,
}: {
  children: ReactNode
  activity?: boolean
  height?: number
}) {
  return (
    <div className={`ema-window ${activity ? 'ema-window--activity' : ''}`} style={{ height }}>
      {children}
    </div>
  )
}

/** Sidebar "3c": controls, brand header, primary action, scrolling navigation, user footer. */
export function Sidebar({
  action,
  children,
  footer,
}: {
  action?: ReactNode
  children: ReactNode
  footer: ReactNode
}) {
  return (
    <aside className="ema-sidebar">
      <div className="ema-sidebar__controls">
        <span className="ema-traffic ema-traffic--red" />
        <span className="ema-traffic ema-traffic--yellow" />
        <span className="ema-traffic ema-traffic--green" />
        <IconButton
          icon={PanelLeft}
          label="Restrânge bara laterală"
          size={28}
          iconSize={16}
          bordered={false}
          className="ema-sidebar__collapse"
        />
      </div>
      <header className="ema-sidebar__brand">
        <BrandMark />
        <span className="ema-sidebar__name">Ema</span>
        <IconButton icon={Search} label="Caută" size={28} iconSize={16} bordered={false} />
      </header>
      {action ?? <span />}
      <nav className="ema-sidebar__nav">{children}</nav>
      {footer}
    </aside>
  )
}

/** The sidebar's primary action "3c" (Lucrare nouă). */
export function NewJobButton({ children, onClick }: { children: ReactNode; onClick?: () => void }) {
  return (
    <button type="button" className="ema-new-job" onClick={onClick}>
      <Icon icon={Plus} size={14} stroke={2} />
      {children}
    </button>
  )
}

/** A navigation group "3c": the section key (ÎN LUCRU, FINALIZATE) and its items. */
export function NavGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="ema-nav-group">
      <span className="ema-nav-group__key">{title}</span>
      {children}
    </div>
  )
}

/** A client in the navigation "3c": a dot in the client's colour (olive, violet for the second). */
export function NavClient({ color, children }: { color: 'olive' | 'violet'; children: ReactNode }) {
  return (
    <span className="ema-nav-client">
      <span className={`ema-nav-client__dot ema-nav-client__dot--${color}`} />
      {children}
    </span>
  )
}

/** A job under its client "3c": active on the surface; a pending count, a spinner, or the check
 * of a finished job. */
export function NavJob({
  active = false,
  count,
  working = false,
  finished = false,
  children,
}: {
  active?: boolean
  count?: number
  working?: boolean
  finished?: boolean
  children: ReactNode
}) {
  return (
    <button type="button" className="ema-nav-job" aria-current={active ? 'page' : undefined}>
      {finished && <Icon icon={Check} size={12} stroke={2.4} color="var(--olive-mark)" />}
      <span className="ema-nav-job__label">{children}</span>
      {count !== undefined && <span className="ema-nav-job__count">{count}</span>}
      {working && <span className="ema-spinner ema-spinner--10" aria-label="în lucru" />}
    </button>
  )
}

/** A settings navigation item "3i": 16px icon, 13.5px, r14; active on the surface. */
export function NavItem({
  icon,
  active = false,
  children,
}: {
  icon: LucideIcon
  active?: boolean
  children: ReactNode
}) {
  return (
    <button type="button" className="ema-nav-item" aria-current={active ? 'page' : undefined}>
      <Icon icon={icon} size={16} stroke={1.6} />
      {children}
    </button>
  )
}

/** The sidebar footer "3c": initials, the user's role, settings. */
export function SidebarFooter({ initials, name }: { initials: string; name: string }) {
  return (
    <div className="ema-sidebar__footer">
      <span className="ema-avatar">{initials}</span>
      <span className="ema-sidebar__user">{name}</span>
      <IconButton icon={Settings} label="Setări" size={26} iconSize={15} bordered={false} />
    </div>
  )
}

/** The content column "3c": the page header (crumb, title, actions) above the page. */
export function Content({
  crumb,
  title,
  actions,
  children,
}: {
  crumb: ReactNode
  title: ReactNode
  actions?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="ema-content">
      <header className="ema-content__header">
        <div className="ema-content__titles">
          <span className="ema-content__crumb">{crumb}</span>
          <h1>{title}</h1>
        </div>
        {actions && <div className="ema-content__actions">{actions}</div>}
      </header>
      {children}
    </section>
  )
}
