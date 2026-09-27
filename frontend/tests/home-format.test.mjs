import assert from 'node:assert/strict'
import test from 'node:test'
import { formatDay } from '../src/home/format.ts'
import { attentionLine, countWords } from '../src/home/count-words.ts'

test('formatDay follows the real calendar and preserves the handoff wording', () => {
  assert.equal(formatDay(new Date(2026, 8, 19)), 'Sâmbătă, 19 septembrie')
  assert.equal(formatDay(new Date(2025, 8, 19)), 'Vineri, 19 septembrie')
})

test('feminine counts and attention sentences', () => {
  assert.deepEqual(
    Array.from({ length: 10 }, (_, index) => countWords(index + 1)),
    ['una', 'două', 'trei', 'patru', 'cinci', 'şase', 'şapte', 'opt', 'nouă', 'zece'],
  )
  assert.equal(countWords(11), '11')
  assert.equal(attentionLine(4, 0), 'toate cele patru lucrări sunt la zi')
  assert.equal(attentionLine(3, 1), 'o lucrare aşteaptă o decizie de la tine')
  assert.equal(attentionLine(3, 2), '2 lucrări aşteaptă o decizie de la tine')
  assert.equal(attentionLine(0, 0), '')
})
