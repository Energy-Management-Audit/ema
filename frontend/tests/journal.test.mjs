import assert from 'node:assert/strict'
import test from 'node:test'
import { journalLine, newestFirst } from '../src/piee/journal.ts'
import { LOG } from './fixtures/piee/default.mjs'

const base = {
  id: 'd',
  at: '2026-09-25T08:00:00Z',
  actor: 'user',
  field_id: 'f',
  on_revision: 1,
  undone_by: null,
}
const number = (value) => ({
  key: 'annual.total_tep',
  label: 'x',
  value,
  unit: 'tep',
  value_type: 'number',
})

test('each action reads as the 3c activity entry', () => {
  assert.deepEqual(
    journalLine(
      { ...base, action: 'choose', before: number('1'), after: number('22161.92') },
      2026,
    ),
    {
      title: 'Total 2025 vs Anexa „Date anuale”',
      detail: 'ales: 22 161,92',
      outcome: 'accepted',
      undoable: true,
    },
  )
  assert.equal(
    journalLine(
      { ...base, action: 'correct', before: number('22164.05'), after: number('22163.5') },
      2026,
    ).detail,
    '22 164,05 → 22 163,50, scris de tine',
  )
  assert.equal(
    journalLine({ ...base, action: 'accept', before: number('1'), after: number('1') }, 2026)
      .detail,
    'acceptat',
  )
  const rejected = journalLine(
    { ...base, action: 'reject', before: number('1'), after: number('1') },
    2026,
  )
  assert.deepEqual([rejected.detail, rejected.outcome], ['respins', 'rejected'])
})

test('undo entries are info; undone entries end in „· anulat” and cannot be undone again', () => {
  const [accepted, corrected, undo] = LOG
  assert.equal(journalLine(accepted, 2026).undoable, true)
  assert.equal(journalLine(corrected, 2026).detail, '230 → 238, scris de tine · anulat')
  assert.equal(journalLine(corrected, 2026).undoable, false)
  assert.deepEqual(
    [journalLine(undo, 2026).outcome, journalLine(undo, 2026).detail],
    ['info', 'anulat'],
  )
  assert.equal(journalLine(undo, 2026).undoable, false)
  assert.deepEqual(
    newestFirst(LOG).map((item) => item.id),
    ['d-3', 'd-2', 'd-1'],
  )
})
