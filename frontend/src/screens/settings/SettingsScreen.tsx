import { StubScreen } from '../../app/StubScreen.tsx'
import type { SettingsGroup } from '../../app/route.ts'

export type SettingsScreenProps = { group: SettingsGroup }

export function SettingsScreen({ group }: SettingsScreenProps) {
  return <StubScreen key={group} title="Setări" />
}
