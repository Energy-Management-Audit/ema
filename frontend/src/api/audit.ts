import { blob, request } from './client.ts'
import type { Decision, Field, RunStart, SlotVersion, VisitView } from './types.ts'
import type { AuditDocuments, AuditOutline, OutlineNode } from './audit-types.ts'

const job = (id: string) => `/jobs/${encodeURIComponent(id)}`

export const auditApi = {
  documents: (id: string) => request<AuditDocuments>('GET', `${job(id)}/audit/documents`),
  outline: (id: string) => request<AuditOutline>('GET', `${job(id)}/audit/outline`),
  visit: (id: string) => request<VisitView>('GET', `${job(id)}/visit`),
  putNote: (id: string, section: string, text: string, revision: number) =>
    request<{ section_id: string; text: string; revision: number }>(
      'PUT',
      `${job(id)}/audit/notes/${encodeURIComponent(section)}`,
      { text, on_revision: revision },
    ),
  putDeadline: (id: string, deadline: string | null, revision: number) =>
    request<{ deadline: string | null; revision: number }>('PUT', `${job(id)}/audit/deadline`, {
      deadline,
      on_revision: revision,
    }),
  patchSection: (
    id: string,
    section: string,
    node: OutlineNode,
    status: 'done' | 'n/a' | 'later' | 'missing' | 'ready' | 'drafted',
    reason?: string,
  ) =>
    request<OutlineNode>('PATCH', `${job(id)}/sections/${encodeURIComponent(section)}`, {
      status,
      on_revision: node.revision,
      ...(reason ? { reason } : {}),
      ...(status === 'done' || status === 'n/a' ? { confirm: true } : {}),
    }),
  patchSections: (id: string, nodes: OutlineNode[]) =>
    request<OutlineNode[]>(
      'PATCH',
      `${job(id)}/sections`,
      nodes.map((node) => ({
        section_id: node.id,
        status: 'done',
        on_revision: node.revision,
        confirm: true,
      })),
    ),
  acceptBatch: (id: string, fields: [string, number][]) =>
    request<Decision[]>('POST', `${job(id)}/fields/accept-batch`, { fields }),
  decide: (id: string, field: Field, action: 'accept' | 'reject' | 'correct', value?: string) =>
    request<Decision>('POST', `${job(id)}/fields/${encodeURIComponent(field.id)}/decide`, {
      action,
      on_revision: field.revision,
      ...(value !== undefined ? { value } : {}),
    }),
  choose: (id: string, field: Field, candidateId: string) =>
    request<Decision>('POST', `${job(id)}/conflicts/${encodeURIComponent(field.id)}`, {
      candidate_id: candidateId,
      on_revision: field.revision,
    }),
  startStage: (id: string, stage: 'intake' | 'read' | 'visit' | 'measures', revision: number) =>
    request<RunStart>('POST', `${job(id)}/stages/${stage}`, { on_revision: revision }),
  measuresForm: () => blob('/audit/forms/masuri-propuse.xlsx'),
  putSlot: (id: string, slot: string, sha: string) =>
    request<SlotVersion>(
      'PUT',
      `${job(id)}/slots/${slot.split('/').map(encodeURIComponent).join('/')}`,
      { file_sha: sha },
    ),
}
