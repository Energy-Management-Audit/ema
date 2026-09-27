import { StubScreen } from '../../app/StubScreen.tsx'
import type { ClientTab } from '../../app/route.ts'

export type ClientScreenProps = { clientId: string; tab: ClientTab }

export function ClientScreen({ clientId, tab }: ClientScreenProps) {
  return <StubScreen key={`${clientId}/${tab}`} title="Clienţi" current="clients" />
}
