import { useEffect, useRef } from 'react'
import { ApiProblem } from '../../api/client.ts'
import { settingsApi } from '../../api/settings.ts'
import { updateApi } from '../../api/update.ts'
import { invalidate, useResource } from '../../state/resource.ts'
import { Button } from '../../ui/Button.tsx'
import { FailureNotice } from '../../ui/Feedback.tsx'
import { GroupBox, GroupRow } from '../../ui/Surface.tsx'

/** 3i: design handoff screen component. */
export function AboutPage() {
  const health = useResource('health', settingsApi.health)
  const update = useResource('update', updateApi.status)
  const refreshCachedUpdate = useRef(Boolean(update.data))
  useEffect(() => {
    if (refreshCachedUpdate.current) invalidate('update')
  }, [])
  const status = update.data
  const updateLink = status?.download_url ?? status?.page_url
  const updateState =
    status?.newer && status.latest
      ? `Versiunea ${status.latest} este disponibilă.`
      : status?.state === 'ok'
        ? 'Ai cea mai nouă versiune.'
        : status?.state === 'no_release'
          ? 'Nicio versiune publicată încă.'
          : status?.state === 'unavailable' || update.error
            ? 'Verificarea nu a reuşit acum; se reîncearcă mai târziu.'
            : 'Se încarcă…'
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
          title="Actualizări"
          description="Ema verifică la pornire dacă există o versiune nouă."
          state={updateState}
          control={
            status?.newer && updateLink ? (
              <a
                className="ema-btn ema-btn--secondary ema-btn--h30 settings-screen__update-link"
                href={updateLink}
                target="_blank"
                rel="noreferrer"
              >
                Descarcă
              </a>
            ) : null
          }
        />
        <GroupRow
          title="Date trimise în afara calculatorului"
          description="Doar către furnizorul de AI ales, pentru cercetare căutări fără date ale clientului, şi pentru verificarea versiunilor noi, fără date."
          control={null}
        />
      </GroupBox>
    </>
  )
}
