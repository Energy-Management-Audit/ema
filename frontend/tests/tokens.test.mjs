// The theme's CSS must carry the handoff README token table exactly, per theme, and paper must
// reset to the light palette. Runs in CI without a browser; the rendered values are checked by
// scripts/capture-s17a.mjs.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const css = readFileSync(new URL('../src/ui/tokens.css', import.meta.url), 'utf8')

const readme = {
  surface: ['#f6f2e8', '#1e1b16'],
  'surface-sunken': ['#f0ebde', '#181510'],
  'surface-raised': ['#f1ecdf', '#242019'],
  'surface-accent': ['#f3ead6', '#2a2419'],
  paper: ['#fffdf6', '#fffdf6'],
  ink: ['#252219', '#ece5d5'],
  'ink-muted': ['rgba(37, 34, 25, 0.72)', 'rgba(236, 229, 213, 0.72)'],
  border: ['rgba(37, 34, 25, 0.11)', 'rgba(236, 229, 213, 0.11)'],
  olive: ['#4f7015', '#9bbb52'],
  amber: ['#b8751a', '#d8a24e'],
  error: ['#9e3f1f', '#e8836a'],
  violet: ['#7a5ea8', '#a58cd4'],
}

function block(selector) {
  const start = css.indexOf(`${selector} {`)
  assert.notEqual(start, -1, `no block for ${selector}`)
  return css.slice(start, css.indexOf('}', start))
}

function declared(body, name) {
  return new RegExp(`--${name}:\\s*([^;]+);`).exec(body)?.[1].trim()
}

const light = block(":root,\n[data-theme='light'],\n.ema-paper")
const dark = block("[data-theme='dark']")

test('light tokens match the README table', () => {
  for (const [name, [value]] of Object.entries(readme))
    assert.equal(declared(light, name), value, name)
})

test('dark tokens match the README table', () => {
  for (const [name, [, value]] of Object.entries(readme))
    assert.equal(declared(dark, name), value, name)
})

test('paper never inverts: it shares the light block and keeps #fffdf6 in dark', () => {
  assert.ok(light.startsWith(":root,\n[data-theme='light'],\n.ema-paper {"))
  assert.equal(declared(dark, 'paper'), '#fffdf6')
})

test('the focus ring is authored from surface and olive', () => {
  assert.match(css, /--focus-ring: 0 0 0 2px var\(--surface\), 0 0 0 4px var\(--olive\);/)
})
