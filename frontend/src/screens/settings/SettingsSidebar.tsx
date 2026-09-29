import { useRef } from 'react'
import { ArrowLeft, Bot, FileText, Folder, SunMedium } from 'lucide-react'
import type { SettingsGroup } from '../../app/route.ts'
import { navigate } from '../../app/navigate.ts'
import { NavGroup, NavItem, Sidebar, SidebarFooter } from '../../ui/Shell.tsx'

const settingsHref = (group: SettingsGroup) => `/app/setari/${group}`

function appPath(url: string): string | null {
  const target = new URL(url, location.href)
  return target.origin === location.origin &&
    target.pathname.startsWith('/app/') &&
    !target.pathname.startsWith('/app/setari')
    ? target.pathname + target.search
    : null
}

function openingPath(): string {
  const navigation = (
    window as Window & {
      navigation?: {
        currentEntry?: { index: number }
        entries: () => { index: number; url: string }[]
      }
    }
  ).navigation
  const current = navigation?.currentEntry?.index
  if (current !== undefined) {
    const entries = navigation?.entries() ?? []
    for (let index = current - 1; index >= 0; index--) {
      const entry = entries.find((item) => item.index === index)
      if (entry) {
        const path = appPath(entry.url)
        if (path) return path
      }
    }
  }
  return (document.referrer && appPath(document.referrer)) || '/app/'
}

/** 3i: design handoff screen component. */
export function SettingsSidebar({ group }: { group: SettingsGroup }) {
  const returnTo = useRef(openingPath())
  const back = () => {
    navigate(returnTo.current)
  }
  return (
    <Sidebar
      action={
        <button type="button" className="settings-sidebar__back" onClick={back}>
          <ArrowLeft size={16} />
          Înapoi la aplicaţie
        </button>
      }
      footer={<SidebarFooter initials="AP" name="Auditor" />}
    >
      <NavGroup title="Lucrul cu documente">
        <NavItem
          icon={FileText}
          active={group === 'extragere'}
          onClick={() => {
            navigate(settingsHref('extragere'))
          }}
        >
          Extragere
        </NavItem>
      </NavGroup>
      <NavGroup title="Calculator">
        <NavItem
          icon={Folder}
          active={group === 'fisiere'}
          onClick={() => {
            navigate(settingsHref('fisiere'))
          }}
        >
          Fişiere şi dosare
        </NavItem>
        <NavItem
          icon={SunMedium}
          active={group === 'aspect'}
          onClick={() => {
            navigate(settingsHref('aspect'))
          }}
        >
          Aspect
        </NavItem>
        <NavItem
          icon={Bot}
          active={group === 'despre'}
          onClick={() => {
            navigate(settingsHref('despre'))
          }}
        >
          Despre Ema
        </NavItem>
      </NavGroup>
    </Sidebar>
  )
}
