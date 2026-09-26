import assert from 'node:assert/strict'
import test from 'node:test'
import { firstWithoutTerm, measureGroups, missingColumns } from '../src/piee/measures.ts'
import { FIELDS } from './fixtures/piee/default.mjs'

test('groups in PIEE order, measures by index', () => {
  const groups = measureGroups(FIELDS)
  assert.deepEqual(
    groups.map((group) => group.title),
    ['SOLUTII EE PLANIFICATE', 'SOLUTII EE', 'AUDIT ENERGETIC'],
  )
  assert.deepEqual(
    groups[0].measures.map((measure) => measure.id),
    ['measure.planned.1', 'measure.planned.2', 'measure.planned.3', 'measure.planned.4'],
  )
  assert.deepEqual(
    measureGroups(FIELDS.filter((f) => !f.key.startsWith('measure.audit'))).length,
    2,
  )
})

test('a column looked for and not found needs an editor; the first measure without a term', () => {
  const planned2 = measureGroups(FIELDS)[0].measures[1]
  assert.deepEqual(missingColumns(planned2), ['commissioning_year'])
  assert.equal(firstWithoutTerm(FIELDS)?.id, 'measure.planned.2')
})
