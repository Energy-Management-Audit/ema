export type ProviderState = {
  present: boolean
  verified_at: string | null
  hint: string | null
  source: 'environment' | 'keyring' | null
}

export type BackupState = {
  dir: string | null
  last_at: string | null
  last_size: number | null
  last_name: string | null
  due: boolean
}

export type SettingsView = {
  theme: 'light' | 'dark'
  default_provider: 'gemini' | 'openai' | null
  providers: Record<'gemini' | 'openai', ProviderState>
  extraction: { ocr: boolean; flag_uncertain: boolean; auto_accept_exact: boolean }
  workspace: string
  backup: BackupState
}

export type BackupResult = {
  name: string
  path: string
  created_at: string
  size_bytes: number
}

export type Health = { status: 'ok'; version: string }
export type ProviderTest = {
  provider: string
  status: 'no_key' | 'ok' | 'failed'
  verified_at: string | null
}
