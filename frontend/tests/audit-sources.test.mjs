import assert from 'node:assert/strict'
import test from 'node:test'
import { sourceLabel } from '../src/audit/sources.ts'

const evidence = { retrieved_at: '2026-09-27T08:00:00Z', provenance: 'document' }
test('source labels keep page, cell, online origin and derivation distinct', () => {
  assert.equal(
    sourceLabel({ ...evidence, locator: { kind: 'pdf_text', page: 3 } }, 'Audit.pdf'),
    'Audit.pdf · pag. 3',
  )
  assert.equal(
    sourceLabel({ ...evidence, locator: { kind: 'cell', sheet: 'Date', ref: 'B2' } }, 'Anexa.xlsx'),
    'Anexa.xlsx · Date!B2',
  )
  assert.match(
    sourceLabel({ ...evidence, locator: { kind: 'url', url: 'https://www.example.org/page' } }),
    /^example.org · /,
  )
  assert.equal(
    sourceLabel({
      ...evidence,
      provenance: 'calculated',
      locator: null,
      derivation: { inputs: ['a', 'b'] },
    }),
    'calculat · 2 intrări',
  )
  assert.equal(
    sourceLabel({ ...evidence, locator: { kind: 'photo' } }, 'Contor.jpg'),
    'Fotografie · Contor.jpg',
  )
})
