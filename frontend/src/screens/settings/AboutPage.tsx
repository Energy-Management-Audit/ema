import { ApiProblem } from '../../api/client.ts'
import { settingsApi } from '../../api/settings.ts'
import { invalidate, useResource } from '../../state/resource.ts'
import { Button } from '../../ui/Button.tsx'
import { FailureNotice } from '../../ui/Feedback.tsx'
import { GroupBox, GroupRow } from '../../ui/Surface.tsx'

export function AboutPage() {
  const health = useResource('health', settingsApi.health)
  return (
    <>
      {health.loading && !health.data && <p className="settings-screen__muted">Se încarcă…</p>}
      {health.error != null && (
        <FailureNotice
          title="Nu am putut încărca versiunea"
          actions={
            <Button
              variant="secondary"
              height={26}
              onClick={() => {
                invalidate('health')
              }}
            >
              Încearcă din nou
            </Button>
          }
        >
          {health.error instanceof ApiProblem
            ? health.error.title
            : 'Cererea nu poate fi procesată.'}
        </FailureNotice>
      )}
      <GroupBox>
        <GroupRow
          title="Versiune"
          description=""
          control={<span className="settings-screen__mono">{health.data?.version ?? '—'}</span>}
        />
        <GroupRow
          title="Date trimise în afara calculatorului"
          description="Doar către furnizorul de AI ales şi, pentru cercetare, căutări fără date ale clientului."
          control={null}
        />
      </GroupBox>
    </>
  )
}
