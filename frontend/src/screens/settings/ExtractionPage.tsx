import { useState } from 'react'
import { ApiProblem } from '../../api/client.ts'
import { settingsApi } from '../../api/settings.ts'
import type { SettingsView } from '../../api/settings-types.ts'
import { invalidate } from '../../state/resource.ts'
import { Toggle } from '../../ui/Field.tsx'
import { FailureNotice } from '../../ui/Feedback.tsx'
import { GroupBox, GroupRow } from '../../ui/Surface.tsx'
import { ProviderKeyRow } from './ProviderKeyRow.tsx'

const ROWS = [
  [
    'ocr',
    'OCR pentru documente scanate',
    'Porneşte singur când un PDF nu are text. Adaugă circa 40 s per document.',
  ],
  [
    'flag_uncertain',
    'Marchează valorile nesigure',
    'Când o valoare apare diferit în două documente, Ema o trece la revizuire în loc să aleagă singură.',
  ],
  [
    'auto_accept_exact',
    'Acceptă automat potrivirile exacte',
    'Rămân în jurnal şi pot fi anulate oricând.',
  ],
] as const

/** 3i: design handoff screen component. */
export function ExtractionPage({ settings }: { settings: SettingsView }) {
  const [problem, setProblem] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const change = async (name: keyof SettingsView['extraction'], value: boolean) => {
    if (busy) return
    setBusy(true)
    setProblem(null)
    try {
      await settingsApi.putSettings({ extraction: { ...settings.extraction, [name]: value } })
      invalidate('settings')
    } catch (error) {
      setProblem(error instanceof ApiProblem ? error.title : 'Cererea nu poate fi procesată.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <h2>Chei API</h2>
      <GroupBox>
        <ProviderKeyRow provider="gemini" state={settings.providers.gemini} settings={settings} />
        <ProviderKeyRow provider="openai" state={settings.providers.openai} settings={settings} />
      </GroupBox>
      <h2>Citire documente</h2>
      <GroupBox>
        {ROWS.map(([key, title, description]) => (
          <GroupRow
            key={key}
            title={title}
            description={description}
            control={
              <Toggle
                checked={settings.extraction[key]}
                label={title}
                onChange={(next) => {
                  void change(key, next)
                }}
              />
            }
          />
        ))}
      </GroupBox>
      {problem && (
        <FailureNotice title={problem} actions={null}>
          {null}
        </FailureNotice>
      )}
    </>
  )
}
