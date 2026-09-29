import { useState } from 'react'
import { ApiProblem } from '../../api/client.ts'
import { settingsApi } from '../../api/settings.ts'
import type { ProviderState, SettingsView } from '../../api/settings-types.ts'
import { rel } from '../../lib/format.ts'
import { invalidate } from '../../state/resource.ts'
import { Button } from '../../ui/Button.tsx'
import { KeyInput } from '../../ui/Field.tsx'
import { GroupRow } from '../../ui/Surface.tsx'
import { Tag } from '../../ui/Chip.tsx'

type Provider = 'gemini' | 'openai'
const COPY = {
  gemini: {
    title: 'Gemini',
    description:
      'Modelul care citeşte documentele şi propune valorile. Dacă ai chei pentru amândouă, Ema o foloseşte pe cea marcată implicit.',
    placeholder: 'AIza…',
    variable: 'EMA_GEMINI_API_KEY',
  },
  openai: {
    title: 'OpenAI',
    description: 'Alternativă la Gemini. Nu e nevoie de amândouă.',
    placeholder: 'sk-…',
    variable: 'EMA_OPENAI_API_KEY',
  },
}

/** 3i: design handoff screen component. */
export function ProviderKeyRow({
  provider,
  state,
  settings,
  testFailed = false,
}: {
  provider: Provider
  state: ProviderState
  settings: SettingsView
  testFailed?: boolean
}) {
  const [key, setKey] = useState('')
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(testFailed)
  const [problem, setProblem] = useState<string | null>(null)
  const copy = COPY[provider]
  const managed = state.source === 'environment'
  const other: Provider = provider === 'gemini' ? 'openai' : 'gemini'
  const both = state.present && settings.providers[other].present

  const save = async () => {
    if (!key.trim() || busy) return
    const value = key
    setKey('')
    setBusy(true)
    setProblem(null)
    try {
      await settingsApi.setKey(provider, value)
      const test = await settingsApi.testProvider(provider)
      setFailed(test.status === 'failed')
      setEditing(false)
      invalidate('settings')
    } catch (error) {
      setProblem(
        error instanceof ApiProblem && error.status === 422
          ? 'Cheia nu poate fi goală.'
          : error instanceof ApiProblem
            ? error.title
            : 'Cererea nu poate fi procesată.',
      )
      invalidate('settings')
    } finally {
      setBusy(false)
    }
  }
  const remove = async () => {
    if (busy) return
    setBusy(true)
    setProblem(null)
    try {
      await settingsApi.removeKey(provider)
      setFailed(false)
      invalidate('settings')
    } catch (error) {
      setProblem(error instanceof ApiProblem ? error.title : 'Cererea nu poate fi procesată.')
    } finally {
      setBusy(false)
    }
  }
  const makeDefault = async () => {
    try {
      await settingsApi.putSettings({ default_provider: provider })
      invalidate('settings')
    } catch (error) {
      setProblem(error instanceof ApiProblem ? error.title : 'Cererea nu poate fi procesată.')
    }
  }
  const status = !state.present
    ? 'fără cheie'
    : managed
      ? `cheie din mediu${state.verified_at ? ` · verificată ${rel(state.verified_at)}` : ''}`
      : failed
        ? 'cheie adăugată · verificarea a eşuat'
        : state.verified_at
          ? `cheie adăugată · verificată ${rel(state.verified_at)}`
          : 'cheie adăugată · neverificată'
  const title = managed
    ? `Cheia e setată în mediul de lucru (${copy.variable}); se schimbă acolo.`
    : undefined
  return (
    <GroupRow
      title={copy.title}
      tag={settings.default_provider === provider ? <Tag>IMPLICIT</Tag> : undefined}
      description={copy.description}
      state={
        <span
          className={`settings-screen__mono ${failed ? 'settings-screen__error' : state.present && state.verified_at ? 'settings-screen__success' : ''}`}
        >
          {status}
          {problem && <span className="settings-screen__error"> · {problem}</span>}
        </span>
      }
      control={
        <div className="settings-key-controls">
          {!state.present || editing ? (
            <>
              <KeyInput
                type="password"
                value={key}
                placeholder={copy.placeholder}
                aria-label={`Cheie ${copy.title}`}
                onChange={(event) => {
                  setKey(event.target.value)
                }}
              />
              <Button
                height={30}
                disabled={!key.trim() || busy}
                loading={busy}
                onClick={() => {
                  void save()
                }}
              >
                {editing ? 'Salvează' : 'Adaugă'}
              </Button>
              {editing && (
                <Button
                  variant="quiet"
                  height={30}
                  onClick={() => {
                    setKey('')
                    setEditing(false)
                    setProblem(null)
                  }}
                >
                  Renunţă
                </Button>
              )}
            </>
          ) : (
            <>
              <span className="settings-screen__mono">{state.hint}</span>
              <Button
                variant="secondary"
                height={30}
                disabled={managed || busy}
                title={title}
                onClick={() => {
                  setEditing(true)
                }}
              >
                Înlocuieşte
              </Button>
              <button
                type="button"
                className="settings-key-controls__remove"
                aria-label="Scoate cheia"
                disabled={managed || busy}
                title={title}
                onClick={() => {
                  void remove()
                }}
              >
                ×
              </button>
            </>
          )}
          {both && settings.default_provider !== provider && (
            <Button
              variant="quiet"
              height={30}
              onClick={() => {
                void makeDefault()
              }}
            >
              Fă-l implicit
            </Button>
          )}
        </div>
      }
    />
  )
}
