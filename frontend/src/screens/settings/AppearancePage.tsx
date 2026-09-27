import { useState } from 'react'
import { ApiProblem } from '../../api/client.ts'
import { settingsApi } from '../../api/settings.ts'
import type { SettingsView } from '../../api/settings-types.ts'
import { invalidate } from '../../state/resource.ts'
import { Toggle } from '../../ui/Field.tsx'
import { FailureNotice } from '../../ui/Feedback.tsx'
import { GroupBox, GroupRow } from '../../ui/Surface.tsx'

export function AppearancePage({ settings }: { settings: SettingsView }) {
  const [problem, setProblem] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const change = async (dark: boolean) => {
    if (busy) return
    setBusy(true)
    setProblem(null)
    const before = settings.theme
    document.documentElement.dataset.theme = dark ? 'dark' : 'light'
    try {
      await settingsApi.putSettings({ theme: dark ? 'dark' : 'light' })
      invalidate('settings')
    } catch (error) {
      document.documentElement.dataset.theme = before
      setProblem(error instanceof ApiProblem ? error.title : 'Cererea nu poate fi procesată.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <GroupBox>
        <GroupRow
          title="Temă întunecată"
          description="Hârtia documentelor rămâne albă în ambele teme."
          control={
            <Toggle
              checked={settings.theme === 'dark'}
              label="Temă întunecată"
              onChange={(dark) => {
                void change(dark)
              }}
            />
          }
        />
      </GroupBox>
      {problem && (
        <FailureNotice title={problem} actions={null}>
          {null}
        </FailureNotice>
      )}
    </>
  )
}
