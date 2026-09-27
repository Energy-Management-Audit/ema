import { StubScreen } from '../../app/StubScreen.tsx'

export type AuditExportScreenProps = { jobId: string }

export function AuditExportScreen({ jobId }: AuditExportScreenProps) {
  return <StubScreen title="Predare" activeJobId={jobId} />
}
