# Ema frontend

React + TypeScript (strict) + Vite. `src/main.tsx` is still the S16a session probe; its only
display is the job count. The versioned API contract is
[`../openapi/ema.v1.json`](../openapi/ema.v1.json).

## Design system (S17a)

`src/ui/` is the component layer from the design handoff (docs/PLAN.md §5.18). `tokens.css` holds
the README token table for both themes; the theme is the `data-theme` attribute (`light` default,
`dark`) on any ancestor, and `.ema-paper` resets the light palette because paper never inverts.
Geist and Geist Mono are bundled from `src/fonts/` (SIL OFL, `OFL.txt`); nothing is loaded from the
network. Component names and comments carry the design id they implement (7d, 3c, 3i, 7b, 7c, M5).

The component sheet is a dev-only entry, not part of the build:

```sh
npm run dev --prefix frontend
# http://127.0.0.1:5173/dev/sheet.html?theme=light   (7d)
# http://127.0.0.1:5173/dev/sheet.html?theme=dark    (7e)
```

Its top frame rebuilds 7d/7e row for row from the real components; the frame below holds the
components the screens use beyond the sheet, each labelled with its design id.

Visual acceptance renders the sheet and the handoff at 1400×900 in both themes, writes paired
screenshots outside git, and asserts tokens per theme, the focus ring, paper in dark, toggle, row
and button states, and the bundled fonts:

```sh
EMA_REFERENCE=… EMA_ARTIFACTS=… npm run capture --prefix frontend   # → $EMA_ARTIFACTS/s17a/
```

`npm run check --prefix frontend` (format, ESLint, tsc, token tests, build) is part of
`scripts/check`.

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
