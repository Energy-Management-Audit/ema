// The one place that talks HTTP (D3). No retries; a problem+json answer becomes an ApiProblem.

export class ApiProblem extends Error {
  readonly code: string
  readonly status: number
  readonly title: string

  constructor(code: string, status: number, title: string) {
    super(title)
    this.code = code
    this.status = status
    this.title = title
  }
}

const CSRF_KEY = 'ema.csrf'

export function storeCsrf(token: string): void {
  localStorage.setItem(CSRF_KEY, token)
}

function csrf(): string {
  return localStorage.getItem(CSRF_KEY) ?? ''
}

let onSessionClosed: (() => void) | null = null

/** E3: any 403 session_required / csrf_required closes the session for the whole app. */
export function watchSession(handler: () => void): void {
  onSessionClosed = handler
}

async function problem(response: Response): Promise<ApiProblem> {
  let code = 'request_error'
  let title = 'Cererea nu poate fi procesată.'
  if (response.headers.get('content-type')?.includes('json')) {
    const body = (await response.json()) as { type?: unknown; title?: unknown }
    if (typeof body.type === 'string') code = body.type.replace('urn:ema:error:', '')
    if (typeof body.title === 'string') title = body.title
  }
  if (code === 'session_required' || code === 'csrf_required') onSessionClosed?.()
  return new ApiProblem(code, response.status, title)
}

async function send(method: string, path: string, body?: unknown): Promise<Response> {
  const headers: Record<string, string> = {}
  let payload: BodyInit | undefined
  if (body instanceof FormData) payload = body
  else if (body !== undefined) {
    headers['content-type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  if (method !== 'GET') headers['x-ema-csrf'] = csrf()
  const response = await fetch(path, { method, headers, body: payload, credentials: 'same-origin' })
  if (!response.ok) throw await problem(response)
  return response
}

export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await send(method, path, body)
  return (await response.json()) as T
}

export async function blob(path: string): Promise<Blob> {
  return (await send('GET', path)).blob()
}
