import assert from 'node:assert/strict'
import test from 'node:test'
import { roCount } from '../src/clients/plural.ts'

test('Romanian counts use singular, plural and de plural at their boundaries', () => {
  assert.equal(roCount(0, 'fişier', 'fişiere'), '0 fişiere')
  assert.equal(roCount(1, 'fişier', 'fişiere'), '1 fişier')
  assert.equal(roCount(2, 'fişier', 'fişiere'), '2 fişiere')
  assert.equal(roCount(19, 'fişier', 'fişiere'), '19 fişiere')
  assert.equal(roCount(20, 'fişier', 'fişiere'), '20 de fişiere')
  assert.equal(roCount(100, 'fişier', 'fişiere'), '100 de fişiere')
  assert.equal(roCount(101, 'fişier', 'fişiere'), '101 fişiere')
  assert.equal(roCount(119, 'fişier', 'fişiere'), '119 fişiere')
  assert.equal(roCount(120, 'fişier', 'fişiere'), '120 de fişiere')
})
