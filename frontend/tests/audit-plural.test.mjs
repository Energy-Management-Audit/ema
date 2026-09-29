import assert from 'node:assert/strict'
import test from 'node:test'
import { noun, plural } from '../src/lib/plural.ts'

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

test('F18 noun-only form follows the same Romanian boundary rule', () => {
  for (const count of [0, 1, 2, 19, 20, 21, 99, 100, 101, 119, 120, 200]) {
    assert.equal(plural(count, 'măsură', 'măsuri'), `${count} ${noun(count, 'măsură', 'măsuri')}`)
  }
  assert.equal(noun(0, 'măsură', 'măsuri'), 'măsuri')
  assert.equal(noun(1, 'măsură', 'măsuri'), 'măsură')
  assert.equal(noun(20, 'măsură', 'măsuri'), 'de măsuri')
  assert.equal(noun(101, 'măsură', 'măsuri'), 'măsuri')
})
