import assert from 'node:assert/strict'
import test from 'node:test'
import { nextStage } from '../src/audit/stages.ts'
import { DOCUMENTS } from './fixtures/audit/default.mjs'

test('next action follows dossier, intake, read, visit, measures, gaps', () => {
  const file = DOCUMENTS.files[0]
  const base = structuredClone(DOCUMENTS)
  assert.equal(nextStage({ ...base, files: [] }).title, 'Lipseşte Necesar info')
  base.files = [file]
  base.runs.intake = null
  assert.equal(nextStage(base).stage, 'intake')
  base.runs.intake = { state: 'ready', current: true }
  base.runs.read = null
  assert.equal(nextStage(base).stage, 'read')
  base.runs.read = { state: 'ready', current: true }
  assert.equal(nextStage(base).stage, 'visit')
  base.runs.visit = { state: 'ready', current: true }
  assert.equal(nextStage(base).stage, 'measures')
  base.runs.measures = { state: 'ready', current: true }
  assert.equal(nextStage(base).filter, 'missing')
  base.missing = []
  assert.equal(nextStage(base), null)
})
