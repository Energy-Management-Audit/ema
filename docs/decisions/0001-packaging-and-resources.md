# 0001 — Windows packaging, and what it demands of the code

Status: accepted · 2026-09-21 · supersedes nothing

## Context

the auditor runs the app on Windows and must not meet Python, a terminal, or an installer that needs
an administrator. The app is one Python process that serves its own UI, so "install" means
shipping a Python runtime plus our dependencies, the built frontend, Tesseract with Romanian data,
the Geist fonts and the auditor's templates.

The previous system failed here in a way worth remembering: its Python worker was frozen
separately from the source it was developed against, so edits silently had no effect and the
worker's errors were discarded.

## Decision

**Build.** PyInstaller in one-folder mode, on a `windows-latest` GitHub runner, triggered by a tag
on `prod`. One-folder starts faster than one-file and draws fewer antivirus false positives.
PyInstaller cannot cross-compile, so this never runs on the development Mac.

**Install.** Inno Setup wraps the folder into `Ema Setup.exe`: per-user installation under
`%LOCALAPPDATA%`, a Start-menu shortcut, an uninstaller, no administrator rights. Unsigned, so
SmartScreen warns on first run; the app checks the latest GitHub release and tells the user when a
newer version exists.

**Run.** FastAPI binds `127.0.0.1` on a free port with a per-launch token; pywebview opens the
window using Edge WebView2, which ships with Windows 10 and 11.

## What this demands of the code, from the first slice

1. **One resources tree, one path helper.** Everything bundled — templates, fonts, Tesseract, the
   frontend build — lives under a single resources directory, and code reaches it only through one
   helper that resolves both the source checkout and the frozen bundle (`sys.frozen`,
   `sys._MEIPASS`). Ad-hoc `Path(__file__).parent / ".."` is how a frozen build breaks in the
   field rather than in CI.
2. **Static imports only.** No dynamic import, no plugin discovery, no module names built from
   strings. PyInstaller cannot see them, and the import contracts cannot check them.
3. **Never write next to the executable.** The installation directory is read-only in practice.
   The workspace defaults to `%APPDATA%\Ema` and is configurable; logs, jobs and outputs live there.
4. **External binaries through configuration.** Tesseract ships with us; Word may
   or may not exist on the machine. Their locations are settings with sensible defaults, never a
   bare `PATH` lookup, and a missing one degrades that feature only.
5. **Threads, not process pools.** A single user's jobs run on worker threads in
   `core.jobs`. Multiprocessing in a frozen app needs `freeze_support()` and pays for
   re-imports; if a hosted version ever needs real workers, it replaces the runner.
6. **One version constant.** `ema.__version__` feeds the update check, the installer and the
   diagnostics bundle.

## Consequences

- The build is only exercised on Windows CI, so packaging problems surface at release time. S18
  adds a smoke test that installs the artefact and runs one job headless.
- macOS is developer-only for now; a signed `.app` would need Apple notarisation.
- Docker and devcontainers are not used: `uv` gives reproducible environments, and a container
  would put Docker Desktop and WSL2 on the auditor's machine for nothing. The code stays
  container-ready (configuration from the environment, no Windows-only code in `core`) because the
  hosted backend will want it later.
