import { startHarness } from './harness.mjs'

export async function withHarness(options, body) {
  const harness = await startHarness(options)
  try {
    await body(harness)
  } finally {
    await harness.close()
  }
}

export const count = (requests, method, path) =>
  requests.filter((item) => item.method === method && item.path === path).length

export async function settle(page) {
  await page.waitForLoadState('networkidle')
}
