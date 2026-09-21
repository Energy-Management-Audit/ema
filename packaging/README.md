# Packaging

The Windows build lives here: the PyInstaller spec and the Inno Setup script, added in slice S18.

Read `docs/decisions/0001-packaging-and-resources.md` first — it is short, and the constraints it
lists (one resources tree, static imports, no writes next to the executable, external binaries
through configuration) apply to every slice before this one.

Nothing in this directory runs on macOS: PyInstaller does not cross-compile, so the build happens
on a Windows runner from a tag on `prod`.
