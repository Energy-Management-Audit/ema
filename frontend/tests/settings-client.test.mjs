import assert from 'node:assert/strict'
import test from 'node:test'
import { ApiProblem, requestVoid } from '../src/api/client.ts'

test('requestVoid resolves 204 and preserves problem mapping', async () => {
  const oldFetch = globalThis.fetch
  const oldStorage = globalThis.localStorage
  globalThis.localStorage = { getItem: () => 'csrf' }
  try {
    globalThis.fetch = async () => new Response(null, { status: 204 })
    await requestVoid('DELETE', '/settings/providers/gemini/key')
    globalThis.fetch = async () =>
      new Response(
        JSON.stringify({
          type: 'urn:ema:error:keyring_unavailable',
          title: 'Depozitul nu este disponibil.',
        }),
        { status: 424, headers: { 'content-type': 'application/problem+json' } },
      )
    await assert.rejects(
      requestVoid('DELETE', '/settings/providers/gemini/key'),
      (error) =>
        error instanceof ApiProblem && error.status === 424 && error.code === 'keyring_unavailable',
    )
  } finally {
    globalThis.fetch = oldFetch
    globalThis.localStorage = oldStorage
  }
})
