import { createRoot } from 'react-dom/client'
import { App } from './app/App.tsx'
import { ApiProblem, storeCsrf } from './api/client.ts'
import { api } from './api/endpoints.ts'
import './ui/base.css'
import './app/app.css'

// D2: the launch code arrives in the fragment (never sent to a server); it is spent on /session,
// the csrf is kept for mutations, and the URL loses the fragment. Everything lives under /app/.
const code = new URLSearchParams(location.hash.slice(1)).get('code')
const path = location.pathname.startsWith('/app') ? location.pathname + location.search : '/app/'
history.replaceState(null, '', path)

async function boot(): Promise<ApiProblem | null> {
  try {
    if (code) storeCsrf((await api.session(code)).csrf)
    document.documentElement.dataset.theme = (await api.settings()).theme
    return null
  } catch (error) {
    return error instanceof ApiProblem
      ? error
      : new ApiProblem('request_error', 0, 'Cererea nu poate fi procesată.')
  }
}

const root = document.getElementById('root')
if (!root) throw new Error('Elementul #root lipseşte.')
void boot().then((problem) => {
  createRoot(root).render(<App bootProblem={problem} />)
})
