import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'

const dialogSource = readFileSync(new URL('../src/ui/Dialog.tsx', import.meta.url), 'utf8')
const functionSource = dialogSource.match(
  /export function nextFocusIndex\(count: number, current: number, backwards: boolean\): number \{[\s\S]*?\n\}/,
)?.[0]

assert.ok(functionSource, 'Dialog.tsx exports nextFocusIndex')
const runnableSource = functionSource.replace(
  'export function nextFocusIndex(count: number, current: number, backwards: boolean): number',
  'function nextFocusIndex(count, current, backwards)',
)
const nextFocusIndex = vm.runInNewContext(
  `(${runnableSource.replace('function nextFocusIndex', 'function')})`,
)

test('nextFocusIndex wraps from the last control to the first', () => {
  assert.equal(nextFocusIndex(3, 2, false), 0)
})

test('nextFocusIndex wraps backward from the first control to the last', () => {
  assert.equal(nextFocusIndex(3, 0, true), 2)
})

test('nextFocusIndex keeps the only control selected', () => {
  assert.equal(nextFocusIndex(1, 0, false), 0)
  assert.equal(nextFocusIndex(1, 0, true), 0)
})

test('nextFocusIndex enters from outside the dialog', () => {
  assert.equal(nextFocusIndex(3, -1, false), 0)
  assert.equal(nextFocusIndex(3, -1, true), 2)
})
