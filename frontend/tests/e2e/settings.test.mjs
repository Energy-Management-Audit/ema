import assert from 'node:assert/strict'
import test from 'node:test'
import { problem } from './harness.mjs'
import { withHarness } from './helpers.mjs'

const empty = {
  theme: 'light',
  default_provider: 'gemini',
  providers: {
    gemini: {
      present: true,
      verified_at: '2026-09-27T08:00:00Z',
      hint: 'AIza••••••••7Kd2',
      source: 'keyring',
    },
    openai: { present: false, verified_at: null, hint: null, source: null },
  },
  extraction: { ocr: true, flag_uncertain: true, auto_accept_exact: false },
  workspace: '/synthetic/workspace',
  backup: { dir: null, last_at: null, last_size: null, last_name: null, due: true },
}

test('settings adds a key, tests it, masks it, and removes it', async () => {
  let current = structuredClone(empty)
  const secret = 'sk-synthetic-secret-1234'
  await withHarness(
    {
      path: '/app/setari/extragere',
      routes: {
        'GET /settings': () => ({ body: current }),
        'PUT /settings/providers/openai/key': () => {
          current = {
            ...current,
            providers: {
              ...current.providers,
              openai: {
                present: true,
                verified_at: null,
                hint: 'sk-s••••••••1234',
                source: 'keyring',
              },
            },
          }
          return { status: 204, body: null }
        },
        'POST /settings/providers/openai/test': {
          body: { provider: 'openai', status: 'ok', verified_at: '2026-09-27T09:00:00Z' },
        },
        'DELETE /settings/providers/openai/key': () => {
          current = {
            ...current,
            providers: { ...current.providers, openai: empty.providers.openai },
          }
          return { status: 204, body: null }
        },
      },
    },
    async ({ page, requests }) => {
      const verified = page.locator('.settings-screen__success').first()
      await verified.waitFor()
      assert.equal(
        await verified.evaluate((element) => getComputedStyle(element).color),
        'rgb(79, 112, 21)',
      )
      assert.equal(
        await verified.evaluate((element) => getComputedStyle(element, '::before').content),
        '""',
      )
      assert.equal(
        await page
          .getByRole('button', { name: 'Scoate cheia' })
          .first()
          .evaluate((element) => getComputedStyle(element).borderTopWidth),
        '0px',
      )
      assert.equal(
        await page
          .locator('.ema-nav-group__key')
          .first()
          .evaluate((element) => getComputedStyle(element).textTransform),
        'none',
      )
      const key = page.getByLabel('Cheie OpenAI')
      await key.fill(secret)
      await page.getByRole('button', { name: 'Adaugă' }).click()
      await page.getByText('sk-s••••••••1234').waitFor()
      assert.equal(
        requests.find(
          (item) => item.path === '/settings/providers/openai/key' && item.method === 'PUT',
        )?.body.key,
        secret,
      )
      assert.ok(requests.some((item) => item.path === '/settings/providers/openai/test'))
      assert.ok(!(await page.content()).includes(secret))
      await page.getByRole('button', { name: 'Scoate cheia' }).last().click()
      await page.getByLabel('Cheie OpenAI').waitFor()
      assert.ok(
        requests.some(
          (item) => item.path === '/settings/providers/openai/key' && item.method === 'DELETE',
        ),
      )
    },
  )
})

test('settings back returns to the entry that opened it after switching pages', async () => {
  await withHarness(
    {
      path: '/app/piee/job-piee-1/date',
      routes: {
        'GET /health': { body: { status: 'ok', version: '0.1.0' } },
      },
    },
    async ({ page }) => {
      await page.getByRole('button', { name: 'Setări' }).click()
      await page.waitForURL('**/app/setari')
      await page.getByRole('button', { name: 'Aspect' }).click()
      await page.waitForURL('**/app/setari/aspect')
      await page.getByRole('button', { name: 'Despre Ema' }).click()
      await page.waitForURL('**/app/setari/despre')
      await page.getByRole('button', { name: 'Înapoi la aplicaţie' }).click()
      await page.waitForURL('**/app/piee/job-piee-1/date')
    },
  )
})

test('settings navigation, keyring replacement and environment row', async () => {
  const managed = {
    ...empty,
    providers: { ...empty.providers, gemini: { ...empty.providers.gemini, source: 'environment' } },
  }
  await withHarness(
    {
      path: '/app/setari/extragere',
      routes: {
        'GET /settings': { body: managed },
        'GET /health': { body: { status: 'ok', version: '0.1.0' } },
      },
    },
    async ({ page }) => {
      assert.equal(await page.getByRole('button', { name: 'Scoate cheia' }).isDisabled(), true)
      assert.match(
        await page.getByRole('button', { name: 'Înlocuieşte' }).getAttribute('title'),
        /EMA_GEMINI_API_KEY/,
      )
      await page.getByRole('button', { name: 'Aspect' }).click()
      await page.waitForURL('**/app/setari/aspect')
      await page.getByRole('button', { name: 'Fişiere şi dosare' }).click()
      await page.waitForURL('**/app/setari/fisiere')
      await page.getByRole('button', { name: 'Despre Ema' }).click()
      await page.waitForURL('**/app/setari/despre')
    },
  )
})

test('replacement can be cancelled and the second key can become default', async () => {
  let current = {
    ...empty,
    providers: {
      ...empty.providers,
      openai: { present: true, verified_at: null, hint: 'sk-s••••••••1234', source: 'keyring' },
    },
  }
  await withHarness(
    {
      path: '/app/setari/extragere',
      routes: {
        'GET /settings': () => ({ body: current }),
        'PUT /settings': () => {
          current = { ...current, default_provider: 'openai' }
          return { body: current }
        },
      },
    },
    async ({ page, requests }) => {
      await page.getByRole('button', { name: 'Fă-l implicit' }).click()
      await page.locator('.ema-group__row').nth(1).getByText('IMPLICIT').waitFor()
      assert.deepEqual(
        requests.find((item) => item.method === 'PUT' && item.path === '/settings')?.body,
        { default_provider: 'openai' },
      )
      await page.getByRole('button', { name: 'Înlocuieşte' }).first().click()
      await page.getByLabel('Cheie Gemini').fill('new-synthetic-key')
      await page.getByRole('button', { name: 'Renunţă' }).click()
      assert.ok(!(await page.content()).includes('new-synthetic-key'))
    },
  )
})

test('toggle sends all extraction values and reverts on a problem; theme applies', async () => {
  let current = structuredClone(empty)
  await withHarness(
    {
      path: '/app/setari/extragere',
      routes: {
        'GET /settings': () => ({ body: current }),
        'PUT /settings': problem('stale_revision', 409, 'Setările s-au schimbat.'),
      },
    },
    async ({ page, requests, setRoute }) => {
      const ocr = page.getByRole('switch', { name: 'OCR pentru documente scanate' })
      await ocr.click()
      await page.getByText('Setările s-au schimbat.').waitFor()
      assert.equal(await ocr.getAttribute('aria-checked'), 'true')
      assert.deepEqual(
        requests.find((item) => item.method === 'PUT' && item.path === '/settings')?.body,
        {
          extraction: { ocr: false, flag_uncertain: true, auto_accept_exact: false },
        },
      )
      setRoute('PUT /settings', () => {
        current = { ...current, theme: 'dark' }
        return { body: current }
      })
      await page.getByRole('button', { name: 'Aspect' }).click()
      await page.getByRole('switch', { name: 'Temă întunecată' }).click()
      await page.waitForFunction(() => document.documentElement.dataset.theme === 'dark')
    },
  )
})

test('backup folder applies on blur and allows a manual copy', async () => {
  let current = structuredClone(empty)
  await withHarness(
    {
      path: '/app/setari/fisiere',
      routes: {
        'GET /settings': () => ({ body: current }),
        'PUT /settings': () => {
          current = { ...current, backup: { ...current.backup, dir: '/synthetic/backups' } }
          return { body: current }
        },
        'POST /backups': () => {
          current = {
            ...current,
            backup: {
              ...current.backup,
              last_at: '2026-09-27T12:00:00Z',
              last_size: 1024,
              last_name: 'ema-backup-synthetic.zip',
              due: false,
            },
          }
          return {
            status: 201,
            body: {
              name: current.backup.last_name,
              path: '/synthetic/backups/ema-backup-synthetic.zip',
              created_at: current.backup.last_at,
              size_bytes: 1024,
            },
          }
        },
      },
    },
    async ({ page, requests }) => {
      await page
        .getByRole('textbox', { name: 'Dosarul pentru copii de siguranţă' })
        .fill('/synthetic/backups')
      await page.getByRole('heading', { name: 'Fişiere şi dosare' }).click()
      await page.getByRole('button', { name: 'Fă o copie acum' }).click()
      await page.getByText(/ultima: .*1 KB/).waitFor()
      assert.deepEqual(
        requests.find((item) => item.method === 'PUT' && item.path === '/settings')?.body,
        { backup_dir: '/synthetic/backups' },
      )
      assert.ok(requests.some((item) => item.path === '/backups'))
    },
  )
})
