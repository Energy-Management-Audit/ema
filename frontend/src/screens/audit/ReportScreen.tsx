import { StubScreen } from '../../app/StubScreen.tsx'

export type ReportScreenProps = { jobId: string }

export function ReportScreen({ jobId }: ReportScreenProps) {
  return <StubScreen title="Raport Word" activeJobId={jobId} />
}
