import assert from 'node:assert/strict'
import test from 'node:test'
import { ApiProblem } from '../src/api/client.ts'
import { api } from '../src/api/endpoints.ts'
import { currentFinal } from '../src/piee/readiness.ts'

const response = {
  approved_at: '2026-09-29T10:00:00Z',
  files: [
    { name: 'Audit-final.docx', path: '/chosen/Audit-final.docx' },
    { name: 'Audit-final.pdf', path: '/chosen/Audit-final.pdf' },
    { name: 'Prelucrare-date.xlsx', path: '/chosen/Prelucrare-date.xlsx' },
  ],
  folder: '/chosen',
}

async function withFetch(fetch, action) {
  const previousFetch = globalThis.fetch
  const previousStorage = globalThis.localStorage
  globalThis.fetch = fetch
  globalThis.localStorage = { getItem: () => 'csrf' }
  try {
    await action()
  } finally {
    globalThis.fetch = previousFetch
    globalThis.localStorage = previousStorage
  }
}

test('P3 export request and ExportResponse match every announced field', async () => {
  for (const destDir of [null, 'C:\\Audits\\Chosen folder']) {
    await withFetch(
      async (url, options) => {
        assert.equal(url, '/jobs/job-1/export')
        assert.equal(options.method, 'POST')
        assert.deepEqual(JSON.parse(options.body), {
          output_id: 'final-1',
          readiness_hash: 'hash-1',
          confirm: true,
          dest_dir: destDir,
        })
        return Response.json(response)
      },
      async () => {
        assert.deepEqual(await api.exportFinal('job-1', 'final-1', 'hash-1', destDir), response)
      },
    )
  }
})

test('P3 checks carries the authoritative final output_id, created_at and file ids or null', async () => {
  const final = {
    output_id: 'final-1',
    created_at: '2026-09-29T10:00:00Z',
    files: ['final-1', 'pdf-1', 'xlsx-1'],
  }
  const outputs = [{ id: 'final-1' }, { id: 'newer-draft', kind: 'draft', version: 99 }]
  for (const selection of [final, null]) {
    const checks = {
      readiness: { draft_ok: true, final_ok: true, blocking: [] },
      readiness_hash: 'hash-1',
      final: selection,
    }
    await withFetch(
      async (url, options) => {
        assert.equal(url, '/jobs/job-1/export/checks')
        assert.equal(options.method, 'GET')
        return Response.json(checks)
      },
      async () => {
        const received = await api.checks('job-1')
        assert.deepEqual(received, checks)
        assert.equal(currentFinal(outputs, received), selection ? outputs[0] : null)
      },
    )
  }
})

for (const code of ['output_stale', 'approval_required']) {
  test(`P3 export preserves ${code} 409`, async () => {
    await withFetch(
      async () =>
        Response.json(
          {
            type: `urn:ema:error:${code}`,
            title: 'Exportul nu este disponibil.',
            status: 409,
          },
          { status: 409, headers: { 'content-type': 'application/problem+json' } },
        ),
      async () => {
        await assert.rejects(
          api.exportFinal('job-1', 'final-1', 'hash-1', null),
          (error) => error instanceof ApiProblem && error.code === code && error.status === 409,
        )
      },
    )
  })
}
