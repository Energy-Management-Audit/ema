import assert from 'node:assert/strict'
import test from 'node:test'
import {
  decided,
  exactBatch,
  filterFields,
  groupByChapter,
  reviewFields,
} from '../src/audit/review.ts'
import { FIELDS } from './fixtures/audit/default.mjs'

test('bulk acceptance excludes uncertain, enriched and photo confirmation fields', () => {
  const exact = FIELDS[0]
  const fields = [
    exact,
    FIELDS[1],
    { ...exact, id: 'enriched', state: 'enriched' },
    { ...exact, id: 'photo', key: 'meter.one', needs_confirmation: true },
    { ...exact, id: 'manual', state: 'manual' },
  ]
  assert.deepEqual(exactBatch(fields), [[exact.id, exact.revision]])
  assert.equal(reviewFields(fields).length, 4)
  assert.deepEqual(
    filterFields(fields, 'uncertain').map((item) => item.id),
    [FIELDS[1].id],
  )
  assert.deepEqual(
    groupByChapter(reviewFields(fields)).map(([chapter]) => chapter),
    ['ch1', 'ch3'],
  )
  const rejected = { ...exact, id: 'rejected', review: 'rejected' }
  assert.equal(decided(rejected), true)
  assert.deepEqual(filterFields([rejected], 'accepted'), [rejected])
})
