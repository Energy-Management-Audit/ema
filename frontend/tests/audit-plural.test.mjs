import assert from 'node:assert/strict'
import test from 'node:test'
import { plural } from '../src/audit/plural.ts'

test('Romanian counted nouns use singular, plural and de at twenty', () => {
  assert.equal(plural(0, 'zi', 'zile'), '0 zile')
  assert.equal(plural(0, 'săptămână', 'săptămâni'), '0 săptămâni')
  assert.equal(plural(0, 'intrare', 'intrări'), '0 intrări')
  assert.equal(plural(1, 'document', 'documente'), '1 document')
  assert.equal(plural(2, 'document', 'documente'), '2 documente')
  assert.equal(plural(19, 'document', 'documente'), '19 documente')
  assert.equal(plural(20, 'document', 'documente'), '20 de documente')
  assert.equal(plural(100, 'document', 'documente'), '100 de documente')
  assert.equal(plural(101, 'document', 'documente'), '101 documente')
  assert.equal(plural(119, 'document', 'documente'), '119 documente')
  assert.equal(plural(120, 'document', 'documente'), '120 de documente')
})
