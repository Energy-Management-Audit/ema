import assert from 'node:assert/strict'
import test from 'node:test'
import { byWeek, decisionLabel, isoWeek, weekRange } from '../src/audit/journal.ts'

test('journal labels human changes and groups across year boundary', () => {
  assert.equal(decisionLabel({ action: 'correct' }), 'scris de tine')
  assert.equal(decisionLabel({ action: 'reject' }), 'respins')
  assert.equal(
    decisionLabel({ action: 'status', target_kind: 'section', after: { status: 'later' } }),
    'Secţiune: mai târziu',
  )
  const statuses = {
    missing: 'lipseşte',
    ready: 'datele sunt gata',
    drafted: 'ciornă gata',
    done: 'gata',
    later: 'mai târziu · vizită',
    'n/a': 'nu se aplică',
    'n/a proposed': 'nu se aplică · propus',
  }
  for (const [status, label] of Object.entries(statuses)) {
    const rendered = decisionLabel({
      action: 'status',
      target_kind: 'section',
      after: { status, reason: status === 'later' ? 'visit' : null },
    })
    assert.equal(rendered, `Secţiune: ${label}`)
    assert.equal(rendered.includes(`: ${status}`), false)
  }
  assert.equal(isoWeek('2025-12-31T12:00:00Z'), '2026-01')
  const weeks = byWeek([{ at: '2026-01-08T12:00:00Z' }, { at: '2025-12-31T12:00:00Z' }])
  assert.deepEqual(
    weeks.map(([week]) => week),
    ['2026-02', '2026-01'],
  )
  assert.match(weekRange('2026-01'), /^29 dec\.–4 ian\./)
})
