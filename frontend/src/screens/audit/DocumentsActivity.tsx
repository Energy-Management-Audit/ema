import type { AuditDocuments } from '../../api/audit-types.ts'
import type { JobStatus } from '../../api/types.ts'
import { plural } from '../../audit/plural.ts'
import { rel } from '../../lib/format.ts'
import { ActivityEntry } from '../../ui/Activity.tsx'
import { Button } from '../../ui/Button.tsx'
import { SectionKey } from '../../ui/Surface.tsx'
import type { DocumentFilter } from './DocumentsTab.tsx'

const stages: Record<string, string> = {
  intake: 'Dosarul citit',
  read: 'Date extrase',
  visit: 'Fotografii înregistrate',
  measures: 'Măsuri citite',
}

export function DocumentsActivity({
  documents,
  status,
  setFilter,
}: {
  documents: AuditDocuments
  status: JobStatus | undefined
  setFilter: (filter: DocumentFilter) => void
}) {
  const needs = documents.files.filter((file) => file.status !== 'read')
  return (
    <div className="audit-documents-activity">
      <SectionKey>CE A APĂRUT</SectionKey>
      {[...(status?.runs ?? [])]
        .filter((run) => run.state !== 'running')
        .slice(-5)
        .reverse()
        .map((run) => (
          <ActivityEntry
            key={run.id}
            outcome={run.state === 'failed' ? 'rejected' : 'info'}
            title={stages[run.stage] ?? run.stage}
            detail={run.state === 'failed' ? 'etapa a eşuat' : undefined}
            time={run.ended_at ? rel(run.ended_at) : ''}
          />
        ))}
      {needs.length > 0 && (
        <div className="audit-activity-next">
          <SectionKey>URMEAZĂ</SectionKey>
          <strong>Verifică {plural(needs.length, 'document', 'documente')}</strong>
          <p>
            {needs
              .slice(0, 3)
              .map((file) => file.reason ?? file.name)
              .join(' · ')}
          </p>
          <Button
            variant="secondary"
            height={28}
            onClick={() => {
              setFilter('verify')
            }}
          >
            Rezolvă acum
          </Button>
        </div>
      )}
    </div>
  )
}
