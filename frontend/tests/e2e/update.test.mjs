import assert from 'node:assert/strict'
import test from 'node:test'
import { available, downloadUrl, tagUrl } from '../fixtures/update/status.mjs'
import { count, settle, withHarness } from './helpers.mjs'

for (const [state, change, expected] of [
  ['newer', {}, 'Versiunea 0.2.0 este disponibilă.'],
  ['current', { latest: '0.1.0', newer: false }, 'Ai cea mai nouă versiune.'],
  [
    'no_release',
    { latest: null, newer: false, state: 'no_release' },
    'Nicio versiune publicată încă.',
  ],
  [
    'unavailable',
    { latest: null, newer: false, state: 'unavailable' },
    'Verificarea nu a reuşit acum; se reîncearcă mai târziu.',
  ],
]) {
  test(`settings shows ${state} update state`, async () => {
    await withHarness(
      {
        path: '/app/setari/despre',
        routes: {
          'GET /health': { body: { status: 'ok', version: '0.1.0' } },
          'GET /settings/update': { body: { ...available, ...change } },
        },
      },
      async ({ page }) => {
        await page.getByText(expected, { exact: true }).waitFor()
        await page
          .getByText(
            'Doar către furnizorul de AI ales, pentru cercetare căutări fără date ale clientului, şi pentru verificarea versiunilor noi, fără date.',
            { exact: true },
          )
          .waitFor()
        const link = page.getByRole('link', { name: 'Descarcă' })
        assert.equal(await link.count(), state === 'newer' ? 1 : 0)
        if (state === 'newer') {
          assert.equal(await link.getAttribute('href'), downloadUrl)
          assert.equal(await link.getAttribute('target'), '_blank')
          assert.equal(await link.getAttribute('rel'), 'noreferrer')
        }
      },
    )
  })
}

for (const newer of [true, false]) {
  test(`home update notice ${newer ? 'appears' : 'stays hidden'}`, async () => {
    await withHarness(
      {
        path: '/app/',
        routes: {
          'GET /settings/update': {
            body: newer ? { ...available, download_url: null } : { ...available, newer: false },
          },
        },
      },
      async ({ page }) => {
        const notice = page.getByText('Există o versiune nouă a Ema (0.2.0)')
        if (newer) {
          await notice.waitFor()
          const link = page.getByRole('link', { name: 'Descarcă' })
          assert.equal(await link.getAttribute('href'), tagUrl)
          assert.equal(await link.getAttribute('target'), '_blank')
        } else {
          await page.getByText('Bine ai revenit.').waitFor()
          assert.equal(await notice.count(), 0)
        }
      },
    )
  })
}

test('returning to a screen refreshes local status through the API cache', async () => {
  await withHarness(
    {
      path: '/app/',
      routes: {
        'GET /health': { body: { status: 'ok', version: '0.1.0' } },
        'GET /settings/update': { body: available },
      },
    },
    async ({ page, requests }) => {
      await page.getByText('Există o versiune nouă a Ema (0.2.0)').waitFor()
      await page.getByRole('button', { name: 'Setări' }).click()
      await page.getByRole('button', { name: 'Despre Ema' }).click()
      await page.getByText('Versiunea 0.2.0 este disponibilă.').waitFor()
      await settle(page)
      assert.equal(count(requests, 'GET', '/settings/update'), 2)
      await page.getByRole('button', { name: 'Înapoi la aplicaţie' }).click()
      await page.getByText('Există o versiune nouă a Ema (0.2.0)').waitFor()
      await settle(page)
      assert.equal(count(requests, 'GET', '/settings/update'), 3)
    },
  )
})
