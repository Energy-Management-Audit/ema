import assert from 'node:assert/strict'
import test from 'node:test'
import {
  clientMatches,
  existingClient,
  matchesClient,
  offersNewClient,
} from '../src/clients/search.ts'

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

const second = { ...client, id: 'client-two', name: 'Șablon B SRL', cui: '98765432', pods: [] }
const nameless = { ...client, id: 'client-three', name: null, cui: null, pods: [] }

test('matches list names containing the text, or CUI digits from three, sorted by name', () => {
  const clients = [second, client, nameless]
  assert.deepEqual(
    clientMatches(clients, 'srl').map((item) => item.id),
    ['client-one', 'client-two'],
  )
  assert.deepEqual(
    clientMatches(clients, 'SABLON').map((item) => item.id),
    ['client-two'],
  )
  assert.deepEqual(
    clientMatches(clients, 'RO 9876').map((item) => item.id),
    ['client-two'],
  )
  assert.deepEqual(clientMatches(clients, '98'), [])
  assert.deepEqual(clientMatches(clients, 'RO001234567890123456'), [])
  assert.equal(clientMatches(clients, '').length, 3)
})

test('the add row is offered for a new name only', () => {
  const clients = [client, second]
  assert.equal(offersNewClient(clients, ''), false)
  assert.equal(offersNewClient(clients, '   '), false)
  assert.equal(offersNewClient(clients, 'client a srl'), false)
  assert.equal(offersNewClient(clients, '  SABLON b srl '), false)
  assert.equal(offersNewClient(clients, 'Client A'), true)
  assert.equal(offersNewClient(clients, 'Client C SRL'), true)
  assert.equal(offersNewClient([], 'Client C SRL'), true)
})

test('an existing client is found by the same name or the same CUI digits', () => {
  const clients = [client, second]
  assert.equal(existingClient(clients, 'client a srl', '')?.id, 'client-one')
  assert.equal(existingClient(clients, 'Nou', 'RO 98765432')?.id, 'client-two')
  assert.equal(existingClient(clients, 'Nou', '98 765'), undefined)
  assert.equal(existingClient(clients, '', ''), undefined)
  assert.equal(existingClient([nameless], 'Nou', ''), undefined)
})
