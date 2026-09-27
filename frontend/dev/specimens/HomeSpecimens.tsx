import { ProviderKeyRow } from '../../src/screens/settings/ProviderKeyRow'
import type { SettingsView } from '../../src/api/settings-types'
import { GroupBox } from '../../src/ui/Surface'
import { SheetFrame, SheetRow, type Theme } from '../SheetParts'

const settings: SettingsView = {
  theme: 'light',
  default_provider: 'gemini',
  providers: {
    gemini: {
      present: true,
      verified_at: '2026-09-27T08:00:00Z',
      hint: 'AIza••••••••7Kd2',
      source: 'keyring',
    },
    openai: { present: false, verified_at: null, hint: null, source: null },
  },
  extraction: { ocr: true, flag_uncertain: true, auto_accept_exact: false },
  workspace: '/synthetic/workspace',
  backup: { dir: null, last_at: null, last_size: null, last_name: null, due: true },
}

export function Specimens({ theme }: { theme: Theme }) {
  const present = settings.providers.gemini
  const absent = settings.providers.openai
  return (
    <SheetFrame id={`home-${theme}`} theme={theme}>
      <div data-capture="home" style={{ display: 'flex', flexDirection: 'column', gap: 26 }}>
        <SheetRow label="ProviderKeyRow · 3i" refs="3i">
          <GroupBox>
            <ProviderKeyRow provider="gemini" state={present} settings={settings} />
            <ProviderKeyRow provider="openai" state={absent} settings={settings} />
            <ProviderKeyRow
              provider="gemini"
              state={{ ...present, source: 'environment' }}
              settings={settings}
            />
            <ProviderKeyRow
              provider="gemini"
              state={{ ...present, verified_at: null }}
              settings={settings}
              testFailed
            />
          </GroupBox>
        </SheetRow>
      </div>
    </SheetFrame>
  )
}
