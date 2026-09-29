import { ApiProblem } from '../../api/client.ts'
import { settingsApi } from '../../api/settings.ts'
import type { SettingsView } from '../../api/settings-types.ts'
import { invalidate, useResource } from '../../state/resource.ts'
import { Button } from '../../ui/Button.tsx'
import { FailureNotice } from '../../ui/Feedback.tsx'
import { Window } from '../../ui/Shell.tsx'
import type { SettingsGroup } from '../../app/route.ts'
import { SettingsSidebar } from './SettingsSidebar.tsx'
import { ExtractionPage } from './ExtractionPage.tsx'
import { FilesPage } from './FilesPage.tsx'
import { AppearancePage } from './AppearancePage.tsx'
import { AboutPage } from './AboutPage.tsx'
import './settings.css'

export type SettingsScreenProps = { group: SettingsGroup }

const TITLES: Record<SettingsGroup, string> = {
  extragere: 'Extragere',
  fisiere: 'Fişiere şi dosare',
  aspect: 'Aspect',
  despre: 'Despre Ema',
}

/** 3i: design handoff screen component. */
export function SettingsScreen({ group }: SettingsScreenProps) {
  const settings = useResource('settings', settingsApi.settings)
  return (
    <Window>
      <SettingsSidebar group={group} />
      <main className="settings-screen">
        <div className="settings-screen__inner">
          <h1>{TITLES[group]}</h1>
          {settings.loading && !settings.data && (
            <p className="settings-screen__muted">Se încarcă…</p>
          )}
          {settings.error != null && (
            <FailureNotice
              title="Nu am putut încărca setările"
              actions={
                <Button
                  variant="secondary"
                  height={26}
                  onClick={() => {
                    invalidate('settings')
                  }}
                >
                  Încearcă din nou
                </Button>
              }
            >
              {settings.error instanceof ApiProblem
                ? settings.error.title
                : 'Cererea nu poate fi procesată.'}
            </FailureNotice>
          )}
          {settings.data && <SettingsPage group={group} settings={settings.data} />}
        </div>
      </main>
    </Window>
  )
}

function SettingsPage({ group, settings }: { group: SettingsGroup; settings: SettingsView }) {
  if (group === 'extragere') return <ExtractionPage settings={settings} />
  if (group === 'fisiere') return <FilesPage key={settings.backup.dir ?? ''} settings={settings} />
  if (group === 'aspect') return <AppearancePage settings={settings} />
  return <AboutPage />
}
