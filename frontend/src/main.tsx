import { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './ui/base.css'

const code = new URLSearchParams(location.hash.slice(1)).get('code')
history.replaceState(null, '', location.pathname)

function App() {
  const [message, setMessage] = useState('Conectare…')

  useEffect(() => {
    async function start() {
      if (!code) throw new Error('Codul de lansare lipseşte.')
      const session = await fetch('/session', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ code }),
      })
      if (!session.ok) throw new Error('Sesiunea nu a putut fi deschisă.')
      const jobs = await fetch('/jobs')
      if (!jobs.ok) throw new Error('Lucrările nu au putut fi încărcate.')
      const list: unknown = await jobs.json()
      if (!Array.isArray(list)) throw new Error('Răspunsul pentru lucrări este invalid.')
      setMessage(`Conectat · ${String(list.length)} lucrări`)
    }

    start().catch((error: unknown) => {
      setMessage(error instanceof Error ? error.message : 'Eroare de conectare.')
    })
  }, [])

  return <main>{message}</main>
}

const root = document.getElementById('root')
if (!root) throw new Error('Elementul #root lipseşte.')
createRoot(root).render(<App />)
