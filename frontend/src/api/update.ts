import { request } from './client.ts'
import type { UpdateInfo } from './update-types.ts'

export const updateApi = {
  status: () => request<UpdateInfo>('GET', '/settings/update'),
}
