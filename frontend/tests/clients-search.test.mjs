import assert from 'node:assert/strict'
import test from 'node:test'
import { matchesClient } from '../src/clients/search.ts'

const client = {
  id: 'client-one',
  name: 'Client A SRL',
  cui: 'RO 12345678',
  county: null,
  caen: null,
  caen_description: null,
  anaf_refreshed_at: null,
  annex_years: [],
  consumption: null,
  pods: ['RO001234567890123456'],
}

test('name ignores case and diacritics; CUI uses three digits; POD uses six characters', () => {
  assert.equal(matchesClient(client, 'CLIENT A'), true)
  assert.equal(matchesClient({ ...client, name: 'Șablon A SRL' }, 'sablon'), true)
  assert.equal(matchesClient(client, '234'), true)
  assert.equal(matchesClient(client, '23'), false)
  assert.equal(matchesClient(client, '456789'), true)
  assert.equal(matchesClient(client, 'RO0012'), true)
  assert.equal(matchesClient(client, '0012'), false)
  assert.equal(matchesClient(client, '  '), true)
})
