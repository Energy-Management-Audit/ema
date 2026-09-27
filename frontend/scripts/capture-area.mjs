import { homedir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { runCapture } from './capture-lib.mjs'

export async function runArea(area) {
  if (!/^[a-z][a-z0-9-]*$/.test(area)) throw new Error('Invalid capture area')
  const { PAIRS, checks } = await import(`./pairs/${area}.mjs`)
  const outFlag = process.argv.indexOf('--out')
  const artifacts = process.env.EMA_ARTIFACTS ?? join(homedir(), 'Code/projects/ema/artifacts')
  const out = outFlag > 0 ? resolve(process.argv[outFlag + 1]) : join(artifacts, `s17b-${area}`)
  await runCapture({ area, pairs: PAIRS, out, extraChecks: checks })
}

if (process.argv[1] === fileURLToPath(import.meta.url)) await runArea(process.argv[2])
