import { execFileSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../..', import.meta.url))
const windowsPython = resolve(root, '.venv/Scripts/python.exe')
const unixPython = resolve(root, '.venv/bin/python')
const python =
  process.env.EMA_PYTHON ??
  (existsSync(windowsPython) ? windowsPython : existsSync(unixPython) ? unixPython : 'python')

export const casePath = (code, ...parts) =>
  execFileSync(python, [resolve(root, 'tests/golden/cases.py'), 'path', code, ...parts], {
    cwd: root,
    env: process.env,
    encoding: 'utf8',
  }).trim()
