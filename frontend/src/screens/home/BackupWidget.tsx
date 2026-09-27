import { useState } from 'react'
import { ApiProblem } from '../../api/client.ts'
import { settingsApi } from '../../api/settings.ts'
import type { BackupState } from '../../api/settings-types.ts'
import { navigate } from '../../app/navigate.ts'
import { formatShortDate } from '../../home/format.ts'
import { invalidate } from '../../state/resource.ts'
import { Button } from '../../ui/Button.tsx'
import { EmaWidget, FailureNotice } from '../../ui/Feedback.tsx'

export function BackupWidget({
  backup,
  onComplete,
}: {
  backup: BackupState
  onComplete: (name: string) => void
}) {
  const [problem, setProblem] = useState<ApiProblem | null>(null)
  const [busy, setBusy] = useState(false)
  const makeBackup = async () => {
    if (busy) return
    setBusy(true)
    setProblem(null)
    try {
      const done = await settingsApi.backupNow()
      onComplete(done.name)
      invalidate('settings')
    } catch (error) {
      setProblem(
        error instanceof ApiProblem
          ? error
          : new ApiProblem('request_error', 0, 'Cererea nu poate fi procesată.'),
      )
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="home-screen__backup">
      <EmaWidget
        title="Un singur lucru, când ai timp"
        actions={
          problem?.code === 'backup_dir_missing' ? (
            <Button
              variant="secondary"
              height={32}
              onClick={() => {
                navigate('/app/setari/fisiere')
              }}
            >
              Alege dosarul
            </Button>
          ) : (
            <Button
              variant="secondary"
              height={32}
              loading={busy}
              disabled={busy}
              onClick={() => {
                void makeBackup()
              }}
            >
              Fă copia acum
            </Button>
          )
        }
      >
        {backup.last_at
          ? `Ultima copie de siguranţă e din ${formatShortDate(backup.last_at)}. Fără ea, o problemă a calculatorului ia cu ea toate lucrările.`
          : 'Nu ai încă nicio copie de siguranţă. Fără ea, o problemă a calculatorului ia cu ea toate lucrările.'}
      </EmaWidget>
      {problem && problem.code !== 'backup_dir_missing' && (
        <FailureNotice title={problem.title} actions={null}>
          {null}
        </FailureNotice>
      )}
    </div>
  )
}
