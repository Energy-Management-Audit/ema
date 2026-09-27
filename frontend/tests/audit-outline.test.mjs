import assert from 'node:assert/strict'
import test from 'node:test'
import { aggregate, countdown, displayTitle, holding, nodeState } from '../src/audit/outline.ts'
import { OUTLINE } from './fixtures/audit/default.mjs'

const node = OUTLINE.nodes[1]
test('all holding states state the specific blocker', () => {
  assert.match(holding({ ...node, status: 'missing' }), /lipsesc/)
  assert.match(holding({ ...node, status: 'ready' }), /datele sunt gata/)
  assert.match(holding({ ...node, status: 'drafted' }), /aşteaptă confirmarea/)
  assert.match(holding({ ...node, status: 'later', reason: 'visit' }), /vizita în teren/)
  assert.match(holding({ ...node, status: 'n/a proposed' }), /nu se aplică/)
  assert.match(
    holding({ ...node, status: 'drafted', stale: true, changed_input: 'Anexa' }),
    /Anexa/,
  )
  assert.equal(holding({ ...node, status: 'done' }), null)
  assert.equal(nodeState({ ...node, status: 'n/a proposed' }), 'nu se aplică · propus')
})

test('aggregate and deadline use applicable sections and calendar days', () => {
  assert.equal(aggregate([{ ...node, status: 'n/a' }]), 'nu se aplică')
  assert.equal(aggregate([{ ...node, status: 'done' }]), 'gata')
  assert.match(aggregate([{ ...node, status: 'later', reason: 'visit' }]), /vizita în teren/)
  assert.equal(displayTitle('DESCRIEREA AUDITULUI'), 'Descrierea auditului')
  assert.equal(
    countdown('2026-10-12', new Date('2026-10-01T12:00:00')),
    'mai sunt 1 săptămână şi 4 zile',
  )
})
