import assert from 'node:assert/strict'
import test from 'node:test'
import { dataWarnings, sourceField } from '../src/audit/warnings.ts'
import { FIELDS } from './fixtures/audit/default.mjs'

test('warnings come from the readiness and default to none', () => {
  const warning = { code: 'data_month_repeat', message: 'm', evidence_ids: ['a', 'b'] }
  assert.deepEqual(dataWarnings(null), [])
  assert.deepEqual(
    dataWarnings({
      readiness: { draft_ok: true, final_ok: true },
      readiness_hash: 'h',
      final: null,
    }),
    [],
  )
  assert.deepEqual(
    dataWarnings({
      readiness: { draft_ok: true, final_ok: true, warnings: [warning] },
      readiness_hash: 'h',
      final: null,
    }),
    [warning],
  )
})

test('a source opens with the field it backs, by value first and then by candidate', () => {
  const candidate = {
    ...FIELDS[1],
    id: 'count',
    evidence: ['evidence-9'],
    alternatives: [{ id: 'alt', value: 3, evidence: ['evidence-8', 'evidence-2'] }],
  }
  const fields = [candidate, ...FIELDS]
  assert.equal(sourceField(fields, 'evidence-1')?.id, FIELDS[0].id)
  assert.equal(sourceField(fields, 'evidence-2')?.id, FIELDS[1].id)
  assert.equal(sourceField(fields, 'evidence-8')?.id, 'count')
  assert.equal(sourceField(fields, 'missing'), undefined)
})
