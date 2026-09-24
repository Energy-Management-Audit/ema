# S16a API probe

The Vite page is a small session and proxy check for S17. Its only display is the job count.
The versioned API contract is [`../openapi/ema.v1.json`](../openapi/ema.v1.json).

## Mock server

From the repository root, one command starts a disposable workspace with synthetic jobs and
examples for every provisional route:

```sh
uv run ema serve --mock --port 8766 --dev-origin http://127.0.0.1:5173
```

In a second terminal:

```sh
npm ci --prefix frontend
npm run dev --prefix frontend
```

Open the fragment URL printed by `ema serve`. Vite proxies `/session`, `/jobs`, `/clients`,
`/evidence`, `/reporting`, `/settings`, and `/openapi.json` to the API. The API checks the backend
Host and the configured Vite Origin. A one-time code in the fragment creates a host-only HttpOnly,
SameSite=Strict cookie; the page removes the fragment before fetching jobs. Mutations also require
the `x-ema-csrf` value returned by `/session`. The proxy keeps both processes on the browser's
`127.0.0.1:5173` origin.

Without `--mock`, the same command uses the configured workspace. Mock mode uses a temporary
workspace and never reads `EMA_REFERENCE`.

For a built frontend smoke check, run `npm run build --prefix frontend` before `ema serve`.
Vite puts the output in `resources/frontend`, which FastAPI serves through the resources path
helper. The generated files are ignored by git; S18 will include that resources tree in the
Windows bundle.

## Contract check

```sh
uv run pytest -q tests/unit/test_api_contract.py
npm run build --prefix frontend
scripts/check
```

The API tests validate OpenAPI 3.1, compare it to the versioned snapshot, call the frozen routes
on temporary workspaces, validate provisional mock payloads against their response schemas,
and exercise correction, re-run, undo, and a synthetic non-Word final export through HTTP.
