import { useState } from 'react'
import { auditApi } from '../../api/audit.ts'
import type { OutlineNode } from '../../api/audit-types.ts'
import { useJob } from '../../state/job.tsx'
import { invalidate } from '../../state/resource.ts'
import { Button } from '../../ui/Button.tsx'
import { Select, TextField } from '../../ui/Field.tsx'

export function SectionActions({ node }: { node: OutlineNode }) {
  const ctx = useJob()
  const [mode, setMode] = useState<'none' | 'na' | 'later'>('none')
  const [reason, setReason] = useState('')
  const [later, setLater] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const patch = async (
    status: 'done' | 'n/a' | 'later' | 'missing' | 'ready' | 'drafted',
    detail?: string,
  ) => {
    setBusy(true)
    setProblem(null)
    try {
      await auditApi.patchSection(ctx.jobId, node.id, node, status, detail)
      ctx.refresh('outline', 'checks', 'log')
      invalidate('overview')
      setMode('none')
    } catch (error) {
      setProblem(error instanceof Error ? error.message : 'Cererea nu poate fi procesată.')
      if (error && typeof error === 'object' && 'status' in error && error.status === 409)
        ctx.refresh('outline')
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="audit-section-actions">
      {node.status === 'drafted' && !node.stale && (
        <Button height={30} disabled={busy} onClick={() => void patch('done')}>
          Marchează gata
        </Button>
      )}
      {node.status === 'n/a proposed' && (
        <>
          <Button
            variant="secondary"
            height={30}
            disabled={busy}
            onClick={() => void patch('n/a', node.reason ?? node.applicability_reason ?? '')}
          >
            Confirmă „nu se aplică”
          </Button>
          <Button
            variant="quiet"
            height={30}
            disabled={busy}
            onClick={() => void patch(node.computed_status)}
          >
            Se aplică
          </Button>
        </>
      )}
      {!node.answered && node.status !== 'n/a proposed' && (
        <>
          <Button
            variant="quiet"
            height={30}
            onClick={() => {
              setMode(mode === 'na' ? 'none' : 'na')
            }}
          >
            Scoate din raport
          </Button>
          <Button
            variant="quiet"
            height={30}
            onClick={() => {
              setMode(mode === 'later' ? 'none' : 'later')
            }}
          >
            Mai târziu
          </Button>
        </>
      )}
      {mode === 'na' && (
        <div className="audit-section-actions__form">
          <TextField
            aria-label="Motiv"
            placeholder="Motiv"
            value={reason}
            onChange={(event) => {
              setReason(event.target.value)
            }}
          />
          <Button
            height={30}
            disabled={!reason.trim() || busy}
            onClick={() => void patch('n/a', reason.trim())}
          >
            Confirmă „nu se aplică”
          </Button>
        </div>
      )}
      {mode === 'later' && (
        <div className="audit-section-actions__form">
          <Select
            placeholder="Aşteaptă"
            value={later}
            onChange={(event) => {
              setLater(event.target.value)
            }}
          >
            <option value="visit">vizita în teren</option>
            <option value="thermography">termografia</option>
            <option value="electrical">măsurătorile electrice</option>
            <option value="map">harta</option>
          </Select>
          <Button height={30} disabled={!later || busy} onClick={() => void patch('later', later)}>
            Salvează
          </Button>
        </div>
      )}
      {problem && (
        <span role="alert" className="audit-error">
          {problem}
        </span>
      )}
    </div>
  )
}
