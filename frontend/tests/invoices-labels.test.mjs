import assert from 'node:assert/strict'
import test from 'node:test'
import {
  formatInvoiceNumber,
  monthName,
  outlierPercent,
  romanianCount,
  statusWord,
} from '../src/invoices/labels.ts'

test('invoice names, status words, ratios and Romanian figures', () => {
  assert.equal(monthName('2026-10'), 'octombrie')
  assert.equal(monthName(null), 'fără lună')
  assert.equal(statusWord('unsupported'), 'nesuportate')
  assert.equal(statusWord('failed'), 'eşuate')
  assert.equal(outlierPercent('1.345'), 35)
  assert.equal(formatInvoiceNumber('1284610'), '1 284 610')
  assert.equal(formatInvoiceNumber('2.1345', 4), '2,1345')
})

test('Romanian count forms at singular, teens, and de-plural boundaries', () => {
  assert.equal(romanianCount(0, 'factură', 'facturi'), '0 facturi')
  assert.equal(romanianCount(1, 'factură', 'facturi'), '1 factură')
  assert.equal(romanianCount(2, 'factură', 'facturi'), '2 facturi')
  assert.equal(romanianCount(19, 'factură', 'facturi'), '19 facturi')
  assert.equal(romanianCount(20, 'factură', 'facturi'), '20 de facturi')
  assert.equal(romanianCount(100, 'factură', 'facturi'), '100 de facturi')
  assert.equal(romanianCount(101, 'factură', 'facturi'), '101 facturi')
  assert.equal(romanianCount(119, 'factură', 'facturi'), '119 facturi')
  assert.equal(romanianCount(120, 'factură', 'facturi'), '120 de facturi')
})
