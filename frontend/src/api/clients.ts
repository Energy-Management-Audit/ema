import { request } from './client.ts'
import type {
  AnnexImport,
  Client,
  ClientOverview,
  ClientProfile,
  Contact,
  Site,
} from './clients-types.ts'

const path = (id: string) => `/clients/${encodeURIComponent(id)}`

export const clientsApi = {
  clientsOverview: () => request<ClientOverview[]>('GET', '/clients/overview'),
  profile: (id: string) => request<ClientProfile>('GET', `${path(id)}/profile`),
  patchClient: (id: string, patch: { contacts?: Contact[]; sites?: Site[] }, revision: number) =>
    request<Client>('PATCH', path(id), { ...patch, on_revision: revision }),
  createFromAnaf: (cui: string) => request<Client>('POST', '/clients/from-anaf', { cui }),
  createClient: (name: string, cui: string) => request<Client>('POST', '/clients', { name, cui }),
  refreshAnaf: (id: string) => request<unknown>('POST', `${path(id)}/anaf/refresh`, {}),
  importAnnexes: (files: File[]) => {
    const form = new FormData()
    for (const file of files) form.append('files', file)
    return request<AnnexImport>('POST', '/clients/annexes', form)
  },
}
