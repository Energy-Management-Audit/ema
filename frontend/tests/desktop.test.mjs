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
const { desktopApi, chooseExportFolder } = await import(
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

test('P3 choose_folder returns the chosen path or cancellation; browser mode uses null destination', async () => {
  const previous = globalThis.window
  try {
    globalThis.window = {}
    assert.deepEqual(await chooseExportFolder(), { path: null })
    for (const result of [{ path: 'C:\\Audits\\Chosen folder' }, null]) {
      let calls = 0
      globalThis.window.pywebview = {
        api: {
          choose_folder: async () => {
            calls += 1
            return result
          },
        },
      }
      assert.deepEqual(await chooseExportFolder(), result)
      assert.equal(calls, 1)
    }
    globalThis.window.pywebview = { api: {} }
    await assert.rejects(chooseExportFolder(), /choose_folder unavailable/)
  } finally {
    globalThis.window = previous
  }
})
