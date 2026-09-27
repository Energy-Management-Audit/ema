// Render the 3c BrandMark as a transparent 256 px source for the Windows icon.
import { readFile, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const root = fileURLToPath(new URL('../..', import.meta.url))
const font = await readFile(`${root}/frontend/src/fonts/Geist-Variable.woff2`)
const browser = await chromium.launch()
try {
  const page = await browser.newPage()
  await page.setContent('<canvas id="icon" width="256" height="256"></canvas>')
  const data = await page.evaluate(async (bytes) => {
    const face = new FontFace('Geist', `url(data:font/woff2;base64,${bytes})`, { weight: '600' })
    document.fonts.add(await face.load())
    const canvas = document.querySelector('#icon')
    const context = canvas.getContext('2d')
    const scale = 256 / 38
    context.fillStyle = '#4f7015'
    context.beginPath()
    context.roundRect(0, 0, 256, 256, [15 * scale, 15 * scale, 15 * scale, 5 * scale])
    context.fill()
    context.font = `600 ${15 * scale}px Geist`
    context.textAlign = 'center'
    context.textBaseline = 'middle'
    context.fillStyle = '#f6f2e8'
    context.fillText('e', 128, 128)
    return canvas.toDataURL('image/png').split(',')[1]
  }, font.toString('base64'))
  await writeFile(`${root}/packaging/ema-icon-256.png`, Buffer.from(data, 'base64'))
} finally {
  await browser.close()
}
