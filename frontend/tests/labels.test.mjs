import assert from 'node:assert/strict'
import test from 'node:test'
import { CARRIERS, MONTHS, carrierLabel, evidenceChip, fieldLabel } from '../src/piee/labels.ts'

test('carrier labels follow M4/M5 and the provisional list', () => {
  assert.equal(carrierLabel('electricity_grid'), 'Energie electrică din SEN')
  assert.equal(carrierLabel('electricity_pv'), 'Energie electrică din parcul fotovoltaic propriu')
  assert.equal(carrierLabel('natural_gas'), 'Gaz natural')
  assert.equal(carrierLabel('diesel'), 'Motorină')
  assert.equal(CARRIERS.clu, 'Combustibil lichid uşor')
  assert.equal(CARRIERS.purchased_heat, 'Energie termică de la terţi')
  assert.equal(Object.keys(CARRIERS).length, 19)
  assert.deepEqual(MONTHS, [
    'Ian',
    'Feb',
    'Mar',
    'Apr',
    'Mai',
    'Iun',
    'Iul',
    'Aug',
    'Sep',
    'Oct',
    'Noi',
    'Dec',
  ])
})

test('field labels for carriers, months, units, the annual total, measures and identity', () => {
  assert.equal(fieldLabel('carrier.natural_gas.2025', 'x', 2026), 'Gaz natural 2025')
  assert.equal(fieldLabel('carrier.natural_gas.2025.03', 'x', 2026), 'Gaz natural · Mar 2025')
  assert.equal(fieldLabel('carrier.natural_gas.2025.unit', 'x', 2026), 'Gaz natural 2025 · unitate')
  assert.equal(fieldLabel('annual.total_tep', 'x', 2026), 'Total 2025 vs Anexa „Date anuale”')
  assert.equal(fieldLabel('measure.planned.2.commissioning_year', 'x', 2026), 'Măsura 2 · termen')
  assert.equal(
    fieldLabel('measure.audit.1.investment_thousand_lei', 'x', 2026),
    'Măsura 1 · investiţie',
  )
  assert.equal(
    fieldLabel('measure.planned.1.saving_thousand_lei', 'x', 2026),
    'Măsura 1 · economie mii lei',
  )
  assert.equal(fieldLabel('identity.name', 'x', 2026), 'Denumire')
  assert.equal(fieldLabel('identity.registrul_comertului', 'x', 2026), 'Nr. Registrul Comerţului')
  assert.equal(fieldLabel('identity.caen_code', 'x', 2026), 'CAEN')
  assert.equal(fieldLabel('identity.contact_person', 'x', 2026), 'Persoană de contact')
  assert.equal(fieldLabel('tep.carrier.x.2025', 'Eticheta', 2026), 'Eticheta')
})

test('source chips name the document and the cell', () => {
  const cell = (method, ref) => ({
    method,
    provenance: 'document',
    locator: { kind: 'cell', sheet: 'Date anuale', ref },
  })
  assert.deepEqual(evidenceChip(cell('anexa', 'Date anuale!F21')), {
    kind: 'document',
    text: 'Anexa 2–3 · Date anuale!F21',
  })
  assert.deepEqual(evidenceChip(cell('questionnaire', 'N23')), {
    kind: 'document',
    text: 'Necesar info · Date anuale!N23',
  })
  assert.equal(evidenceChip(cell('prelucrare', 'X!D11')).text, 'Prelucrare · X!D11')
  assert.equal(evidenceChip(cell('invoice', 'X!A1')).text, 'Factură · X!A1')
  assert.deepEqual(evidenceChip({ method: 'calc', provenance: 'calculated' }), {
    kind: 'calculated',
    text: 'calculat',
  })
  assert.deepEqual(evidenceChip({ method: 'manual', provenance: 'manual' }), {
    kind: 'manual',
    text: 'introdus manual',
  })
})
