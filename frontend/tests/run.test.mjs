import assert from 'node:assert/strict'
import test from 'node:test'
import { runReducer, startRun, terminalFor } from '../src/state/run.ts'

const event = (type, payload = {}, run = 'run-1') => ({
  seq: 1,
  job_id: 'job',
  run_id: run,
  stage: 'piee_generate',
  type,
  at: '2026-09-25T08:00:00+00:00',
  payload,
})

test('the reducer folds one run and ignores the others', () => {
  let state = startRun('run-1', 'piee_generate')
  state = runReducer(state, event('stage_started'))
  assert.equal(state.startedAt, '2026-09-25T08:00:00+00:00')
  state = runReducer(
    state,
    event('stage_progress', { done: 1, total: 2, message: 'Ciornă generată' }),
  )
  assert.equal(`${state.message} ${state.done}/${state.total}`, 'Ciornă generată 1/2')
  const ignored = runReducer(
    state,
    event('stage_progress', { done: 2, total: 2, message: 'x' }, 'run-2'),
  )
  assert.equal(ignored, state)
  state = runReducer(state, event('item_failed'))
  assert.equal(state.itemFailures, 1)
  state = runReducer(state, event('stage_finished', { state: 'ready', publication: 'current' }))
  assert.equal(state.state, 'ready')
  assert.equal(state.publication, 'current')
})

test('failed and cancelled runs, and the terminal rebuilt from a stored state', () => {
  assert.equal(
    runReducer(startRun('run-1', 's'), event('stage_failed', { code: 'x' })).state,
    'failed',
  )
  assert.equal(runReducer(startRun('run-1', 's'), event('stage_cancelled')).state, 'cancelled')
  assert.equal(terminalFor(startRun('run-1', 's'), 'ready')?.type, 'stage_finished')
  assert.equal(terminalFor(startRun('run-1', 's'), 'failed')?.type, 'stage_failed')
  assert.equal(terminalFor(startRun('run-1', 's'), 'running'), null)
})
