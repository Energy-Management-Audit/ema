import { useState } from 'react'
import { ApiProblem } from '../../api/client.ts'
import { settingsApi } from '../../api/settings.ts'
import type { SettingsView } from '../../api/settings-types.ts'
import { formatBackupTime } from '../../home/format.ts'
import { formatBytes } from '../../lib/format.ts'
import { invalidate } from '../../state/resource.ts'
import { Button } from '../../ui/Button.tsx'
import { TextField } from '../../ui/Field.tsx'
import { FailureNotice } from '../../ui/Feedback.tsx'
import { GroupBox, GroupRow } from '../../ui/Surface.tsx'

export function FilesPage({ settings }: { settings: SettingsView }) {
  const [folder, setFolder] = useState(settings.backup.dir ?? '')
  const [folderError, setFolderError] = useState<string | null>(null)
  const [backupError, setBackupError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const apply = async () => {
    if (folder === (settings.backup.dir ?? '')) return
    setFolderError(null)
    try {
      await settingsApi.putSettings({ backup_dir: folder.trim() || null })
      invalidate('settings')
    } catch (error) {
      setFolderError(error instanceof ApiProblem ? error.title : 'Cererea nu poate fi procesată.')
    }
  }
  const makeBackup = async () => {
    if (busy || !settings.backup.dir) return
    setBusy(true)
    setBackupError(null)
    try {
      await settingsApi.backupNow()
      invalidate('settings')
    } catch (error) {
      setBackupError(error instanceof ApiProblem ? error.title : 'Cererea nu poate fi procesată.')
    } finally {
      setBusy(false)
    }
  }
  const backupState =
    settings.backup.last_at && settings.backup.last_size != null
      ? `ultima: ${formatBackupTime(settings.backup.last_at)} · ${formatBytes(settings.backup.last_size)}`
      : 'încă nicio copie'
  return (
    <>
      <GroupBox>
        <GroupRow
          title="Spaţiul de lucru"
          description="Aici sunt lucrările, fişierele primite şi documentele generate."
          control={<span className="settings-screen__mono">{settings.workspace}</span>}
        />
        <GroupRow
          title="Dosarul pentru copii de siguranţă"
          description="Ema scrie aici copia săptămânală: un disc extern sau un dosar sincronizat (OneDrive)."
          state={
            folderError && (
              <span className="settings-screen__error" role="alert">
                {folderError}
              </span>
            )
          }
          control={
            <TextField
              className="settings-screen__mono"
              aria-label="Dosarul pentru copii de siguranţă"
              value={folder}
              onChange={(event) => {
                setFolder(event.target.value)
              }}
              onBlur={() => {
                void apply()
              }}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault()
                  event.currentTarget.blur()
                }
              }}
            />
          }
        />
        <GroupRow
          title="Copie de siguranţă"
          description=""
          state={<span className="settings-screen__mono">{backupState}</span>}
          control={
            <Button
              variant="secondary"
              height={30}
              loading={busy}
              disabled={!settings.backup.dir || busy}
              onClick={() => {
                void makeBackup()
              }}
            >
              Fă o copie acum
            </Button>
          }
        />
      </GroupBox>
      {backupError && (
        <FailureNotice title={backupError} actions={null}>
          {null}
        </FailureNotice>
      )}
      <p className="settings-screen__note">
        Pentru siguranţa datelor clienţilor, ţine discul calculatorului criptat (BitLocker pe
        Windows, FileVault pe Mac).
      </p>
    </>
  )
}
