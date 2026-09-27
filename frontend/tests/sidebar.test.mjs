import assert from 'node:assert/strict'
import test from 'node:test'
import {
  finalizedJobs,
  finalizedLabel,
  groupInProgress,
  jobLabel,
  moreLabel,
} from '../src/app/sidebar.ts'

const at = (hour) => `2026-09-27T${String(hour).padStart(2, '0')}:00:00Z`
const item = (id, type, client_slug, year, hour, extra = {}) => ({
  id,
  type,
  client_slug,
  client_name: null,
  year,
  state: 'ready',
  revision: 1,
  created_at: at(hour),
  updated_at: at(hour),
  final_ok: false,
  blocking: 0,
  next: null,
  readiness_error: null,
  approved_at: null,
  finalized: false,
  ...extra,
})

test('in-progress jobs group by latest client activity and sort by workflow then year', () => {
  const jobs = [
    item('p1', 'piee', 'first', 2025, 8),
    item('a1', 'audit', 'first', 2026, 9, { client_name: 'First SA' }),
    item('i1', 'invoices', 'second', 2026, 10),
    item('a2', 'audit', 'second', 2024, 7),
    item('i2', 'invoices', 'first', 2024, 6),
    item('r', 'reporting', 'reporting', null, 11),
  ]
  const groups = groupInProgress(jobs)
  assert.deepEqual(
    groups.map((group) => [group.slug, group.color]),
    [
      ['second', 'olive'],
      ['first', 'violet'],
    ],
  )
  assert.deepEqual(
    groups[0].jobs.map((job) => job.id),
    ['a2', 'i1'],
  )
  assert.deepEqual(
    groups[1].jobs.map((job) => job.id),
    ['a1', 'i2', 'p1'],
  )
  assert.equal(groups[1].name, 'First SA')
})

test('labels, finalized order and expansion words follow the handoff', () => {
  assert.equal(jobLabel(item('a', 'audit', 'c', 2026, 1)), 'Audit energetic 2026')
  assert.equal(jobLabel(item('p', 'piee', 'c', 2026, 1)), 'PIEE 2026')
  assert.equal(jobLabel(item('i', 'invoices', 'c', null, 1)), 'Facturi')
  const finished = finalizedJobs([
    item('a', 'audit', 'c', 2025, 1, { finalized: true, approved_at: at(8) }),
    item('p', 'piee', 'c', 2026, 2, { finalized: true, approved_at: at(9) }),
    item('i', 'invoices', 'c', 2026, 3, { finalized: true }),
  ])
  assert.deepEqual(
    finished.map((job) => job.id),
    ['p', 'a', 'i'],
  )
  assert.equal(finalizedLabel(finished[0]), 'PIEE c 2026')
  assert.equal(moreLabel(1), 'încă una…')
  assert.equal(moreLabel(2), 'încă două…')
  assert.equal(moreLabel(3), 'încă 3…')
})
