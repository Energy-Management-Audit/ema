import assert from 'node:assert/strict'
import test from 'node:test'
import { attachBlobUrl } from '../src/api/blobUrl.ts'

test('blob URL lifecycle revokes the loaded URL on cleanup', async () => {
  const create = URL.createObjectURL
  const revoke = URL.revokeObjectURL
  const revoked = []
  URL.createObjectURL = () => 'blob:synthetic'
  URL.revokeObjectURL = (url) => {
    revoked.push(url)
  }
  try {
    let shown = null
    const cleanup = attachBlobUrl(
      async () => new Blob(['image']),
      (url) => {
        shown = url
      },
    )
    await Promise.resolve()
    assert.equal(shown, 'blob:synthetic')
    cleanup()
    assert.deepEqual(revoked, ['blob:synthetic'])
  } finally {
    URL.createObjectURL = create
    URL.revokeObjectURL = revoke
  }
})

test('cleanup before fetch completes creates no URL', async () => {
  const create = URL.createObjectURL
  let calls = 0
  URL.createObjectURL = () => {
    calls += 1
    return 'blob:synthetic'
  }
  try {
    let resolve
    const load = new Promise((done) => {
      resolve = done
    })
    const cleanup = attachBlobUrl(
      () => load,
      () => {
        throw new Error('late URL')
      },
    )
    cleanup()
    resolve(new Blob(['image']))
    await Promise.resolve()
    assert.equal(calls, 0)
  } finally {
    URL.createObjectURL = create
  }
})
