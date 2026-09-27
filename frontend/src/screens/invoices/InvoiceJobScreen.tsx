import { StubScreen } from '../../app/StubScreen.tsx'

export type InvoiceJobScreenProps = { jobId: string }

export function InvoiceJobScreen({ jobId }: InvoiceJobScreenProps) {
  return <StubScreen title="Facturi" activeJobId={jobId} />
}
