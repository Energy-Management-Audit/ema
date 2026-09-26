import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '../src/ui/base.css'
import './sheet.css'
import { ComponentSheet } from './ComponentSheet'
import { Extensions } from './Extensions'
import { PieeSpecimens } from './PieeSpecimens'

// Dev-only entry (not in the build): /dev/sheet.html?theme=light|dark
const theme = new URLSearchParams(location.search).get('theme') === 'dark' ? 'dark' : 'light'
const id = theme === 'dark' ? '7e' : '7d'

function Page() {
  return (
    <main className="sheet-page">
      <nav className="sheet-page__themes">
        <a href="?theme=light" aria-current={theme === 'light' ? 'page' : undefined}>
          7d clar
        </a>
        <a href="?theme=dark" aria-current={theme === 'dark' ? 'page' : undefined}>
          7e întunecat
        </a>
      </nav>
      <p className="sheet-page__caption">
        <b>{id}</b>
        {theme === 'dark'
          ? 'Aceeaşi foaie, tema întunecată — fiecare componentă verificată pe #1e1b16, nu doar declarată în tabelul de tokenuri'
          : 'Foaia de componente — inventarul pentru implementare'}
      </p>
      <ComponentSheet theme={theme} />
      <p className="sheet-page__caption">
        <b>+</b>Extensii — componentele din ecrane care nu sunt pe foaia {id}, fiecare cu id-ul de
        design de unde vine
      </p>
      <Extensions theme={theme} />
      <p className="sheet-page__caption">
        <b>S17b</b>Componentele ecranelor PIEE (3g, 7a)
      </p>
      <PieeSpecimens theme={theme} />
    </main>
  )
}

const root = document.getElementById('root')
if (!root) throw new Error('#root is missing from sheet.html')
createRoot(root).render(
  <StrictMode>
    <Page />
  </StrictMode>,
)
