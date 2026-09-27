import assert from 'node:assert/strict'
import test from 'node:test'
import { invoiceView } from '../src/invoices/view.ts'

const slot = ['invoices/0001']
const ready = [{ id: 'r1', stage: 'invoices', state: 'ready', publication: 'current' }]

test('invoice view follows the five states and ignores stale runs', () => {
  assert.equal(invoiceView({ slots: [], runs: ready, confirmed: true }), 'empty')
  assert.equal(
    invoiceView({ slots: slot, runs: [{ ...ready[0], state: 'running' }], confirmed: null }),
    'reading',
  )
  assert.equal(invoiceView({ slots: slot, runs: [], confirmed: null }), 'unread')
  assert.equal(
    invoiceView({ slots: slot, runs: [{ ...ready[0], publication: 'stale' }], confirmed: true }),
    'unread',
  )
  assert.equal(invoiceView({ slots: slot, runs: ready, confirmed: false }), 'identity')
  assert.equal(invoiceView({ slots: slot, runs: ready, confirmed: true }), 'table')
})
