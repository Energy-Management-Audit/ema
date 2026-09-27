export type UpdateInfo = {
  current: string
  latest: string | null
  newer: boolean
  notes: string | null
  page_url: string | null
  download_url: string | null
  checked_at: string
  state: 'ok' | 'no_release' | 'unavailable'
}
