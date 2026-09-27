import assert from 'node:assert/strict'
import test from 'node:test'
import { statusLine } from '../src/home/status.ts'

const base = { state: 'created', readiness_error: null, final_ok: false, next: null }

test('home status uses the ordered branches', () => {
  assert.equal(
    statusLine({ ...base, state: 'running', readiness_error: 'missing' }),
    'se lucrează…',
  )
  assert.equal(statusLine({ ...base, readiness_error: 'missing' }), 'aşteaptă documentele')
  assert.equal(statusLine({ ...base, final_ok: true }), 'gata de exportul final')
  assert.equal(statusLine({ ...base, next: 'Adaugă fişierul' }), 'Adaugă fişierul')
  assert.equal(statusLine(base), 'în lucru')
})
