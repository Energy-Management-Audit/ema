# Windows build

The Windows workflow builds one PyInstaller folder, wraps it in a per-user Inno Setup installer,
then installs, exercises, and uninstalls it on a fresh runner. The bundle copies the package
metadata listed in `metadata.txt` with `copy_metadata`; `tests/unit/test_packaging_metadata.py`
checks that the list is sufficient without entry-point discovery.

## Build on Windows

From the repository root with Node 24, uv, and Inno Setup 7.1.0:

```powershell
npm ci --prefix frontend
npm run build --prefix frontend
./packaging/fetch_tesseract.ps1
uv sync --frozen --no-dev --group packaging
uv run --no-sync pyinstaller packaging/ema.spec --noconfirm --distpath build/dist --workpath build/work
& "$env:ISCC" /DAppVersion=0.1.0 packaging\ema.iss
```

`build/dist/Ema/` contains `Ema.exe` (the desktop window), `ema-cli.exe` (console commands),
and `_internal/` (Python, frontend, Tesseract, and other resources). The installer lands in
`build/installer/Ema-Setup-<version>.exe`. Both executables use the same code and workspace.
`Ema.exe` with no arguments opens the window; `ema-cli.exe check-install` prints JSON diagnostics.

The workflow's smoke command is `./packaging/smoke.ps1`. It installs the artifact for the current
user, checks OCR and resources, extracts the synthetic invoice in `packaging/smoke`, starts the
local server, compares the installed folder before and after use, and uninstalls while preserving
the workspace at `%APPDATA%\Ema`.

## Release

Update both `ema.__version__` and `pyproject.toml` to the same version. Merge to `prod`, then
create and push an annotated `v<version>` tag on that commit. Its annotation is the Romanian
release note. A prod tag runs Windows unit tests, build, smoke, and publish to the public
`Energy-Management-Audit/ema-releases` repository. `RELEASES_TOKEN` must be configured for
publication; an unset token fails the publish job.
