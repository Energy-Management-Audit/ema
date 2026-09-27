import type { ReactNode } from 'react'
import { AppSidebar } from '../app/AppSidebar.tsx'
import { ApiProblem } from '../api/client.ts'
import { EmptyState, FailureNotice } from '../ui/Feedback'
import { Button } from '../ui/Button'
import { Window } from '../ui/Shell'

export function problemTitle(error: unknown): string {
  return error instanceof ApiProblem ? error.title : 'Cererea nu poate fi procesată.'
}

function Bare({ children, sidebar = true }: { children: ReactNode; sidebar?: boolean }) {
  return (
    <Window>
      {sidebar ? <AppSidebar current="home" /> : <span />}
      <section className="ema-content app-center">{children}</section>
    </Window>
  )
}

/** E0: no PIEE job yet. */
export function NoJob() {
  return (
    <Bare>
      <EmptyState mark="brand" title="Nicio lucrare PIEE încă" actions={null}>
        Lucrările PIEE apar aici după ce sunt create.
      </EmptyState>
    </Bare>
  )
}

/** E3: the session cookie is gone; only a new launch helps. */
export function SessionClosed() {
  return (
    <Bare sidebar={false}>
      <EmptyState mark="brand" title="Sesiunea s-a închis" actions={null}>
        Porneşte Ema din nou ca să continui.
      </EmptyState>
    </Bare>
  )
}

/** E2 outside a job: the first reads failed. */
export function BootFailure({ problem }: { problem: unknown }) {
  return (
    <Bare sidebar={false}>
      <FailureNotice
        title="Nu am putut încărca lucrarea"
        actions={
          <Button
            variant="secondary"
            height={32}
            onClick={() => {
              location.reload()
            }}
          >
            Încearcă din nou
          </Button>
        }
      >
        {problemTitle(problem)}
      </FailureNotice>
    </Bare>
  )
}
