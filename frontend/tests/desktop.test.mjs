import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'

const source = readFileSync(
  fileURLToPath(new URL('../src/lib/desktop.ts', import.meta.url)),
  'utf8',
)
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
const { desktopApi } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
)

test('desktop bridge is present only with both public file methods', () => {
  const previous = globalThis.window
  try {
    globalThis.window = {}
    assert.equal(desktopApi(), null)
    globalThis.window.pywebview = { api: { save_output() {} } }
    assert.equal(desktopApi(), null)
    const api = { save_output() {}, open_output() {} }
    globalThis.window.pywebview = { api }
    assert.equal(desktopApi(), api)
  } finally {
    globalThis.window = previous
  }
})
