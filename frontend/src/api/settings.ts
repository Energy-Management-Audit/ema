import { request, requestVoid } from './client.ts'
import type { BackupResult, Health, ProviderTest, SettingsView } from './settings-types.ts'

type Provider = 'gemini' | 'openai'
type Patch = Partial<Pick<SettingsView, 'theme' | 'default_provider' | 'extraction'>> & {
  backup_dir?: string | null
}
const providerPath = (provider: Provider) => `/settings/providers/${provider}`

export const settingsApi = {
  settings: () => request<SettingsView>('GET', '/settings'),
  health: () => request<Health>('GET', '/health'),
  putSettings: (patch: Patch) => request<SettingsView>('PUT', '/settings', patch),
  setKey: (provider: Provider, key: string) =>
    requestVoid('PUT', `${providerPath(provider)}/key`, { key }),
  removeKey: (provider: Provider) => requestVoid('DELETE', `${providerPath(provider)}/key`),
  testProvider: (provider: Provider) =>
    request<ProviderTest>('POST', `${providerPath(provider)}/test`, {}),
  backupNow: () => request<BackupResult>('POST', '/backups', {}),
}
