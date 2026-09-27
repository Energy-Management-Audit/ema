import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import test from 'node:test'

const contract = JSON.parse(
  readFileSync(new URL('../../openapi/ema.v1.json', import.meta.url), 'utf8'),
)
const apiDir = new URL('../src/api/', import.meta.url)
const source = ['types.ts', ...readdirSync(apiDir).filter((file) => file.endsWith('-types.ts'))]
  .map((file) => readFileSync(new URL(file, apiDir), 'utf8'))
  .join('\n')

function declaredTypes() {
  const types = new Map()
  for (const match of source.matchAll(/export type (\w+) = \{\n([\s\S]*?)\n\}/g)) {
    const names = [...match[2].matchAll(/^ {2}(\w+)\??:/gm)].map((item) => item[1])
    types.set(match[1], names)
  }
  return types
}

test('frontend API property names equal the OpenAPI schemas', () => {
  const schemas = contract.components.schemas
  const types = declaredTypes()
  const checked = []
  for (const [name, properties] of types) {
    const schema = schemas[name]
    if (!schema) continue
    checked.push(name)
    assert.deepEqual([...properties].sort(), Object.keys(schema.properties ?? {}).sort(), name)
  }
  for (const name of [
    'Job',
    'JobOverview',
    'Field',
    'Decision',
    'Evidence',
    'Output',
    'Approval',
    'PieeSummary',
    'ExportChecks',
  ]) {
    assert.ok(checked.includes(name), `${name} is mirrored`)
  }
})
