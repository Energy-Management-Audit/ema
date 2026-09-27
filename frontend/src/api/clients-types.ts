export type Site = { id: string; name: string; address: string | null }
export type Contact = { id: string; name: string; role: string | null }
export type Client = {
  id: string
  name: string | null
  cui: string | null
  caen: string | null
  sites: Site[]
  contacts: Contact[]
  revision: number
  anaf_refreshed_at: string | null
}
export type ClientOverview = {
  id: string
  name: string | null
  cui: string | null
  county: string | null
  caen: string | null
  caen_description: string | null
  anaf_refreshed_at: string | null
  annex_years: number[]
  consumption: { year: number; total_tep: string } | null
  pods: string[]
}
export type Identification = {
  name: string | null
  cui: string | number | null
  registration: string | null
  address: string | null
  caen: string | number | null
  caen_description: string | null
  source: 'anaf' | 'annex'
  retrieved_at: string | null
  annex_year: number | null
}
export type ClientProfile = {
  client: Client
  identification: Identification | null
  fiscal: { active: boolean | null; vat_payer: boolean | null } | null
  energy_manager: Contact | null
  contact_person: { name: string; source: 'client' | 'annex'; annex_year: number | null } | null
  memory: {
    kind: string
    identifier: string
    job_id: string
    confirmed_at: string
    active: boolean
  }[]
  annexes: { sha: string; year: number; file_name: string | null; read_at: string }[]
}
export type AnnexImport = {
  imported: {
    file_name: string
    client_id: string
    client_name: string | null
    created: boolean
    year: number
    sha: string
  }[]
  ignored: { file_name: string; code: string; reason: string }[]
}
