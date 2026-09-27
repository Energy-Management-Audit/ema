"""One resource tree and two entry points in one frozen folder."""

from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata

spec_dir = Path(SPECPATH)
metadata_names = [
    line.split("#", 1)[0].strip()
    for line in (spec_dir / "metadata.txt").read_text(encoding="utf-8").splitlines()
    if line.split("#", 1)[0].strip()
]
metadata = [item for name in metadata_names for item in copy_metadata(name)]

a = Analysis(
    [str(spec_dir / "entry.py")],
    pathex=[str(spec_dir.parent / "src")],
    binaries=[],
    datas=[(str(spec_dir.parent / "resources"), "resources"), *metadata],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe_gui = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Ema",
    console=False,
    icon=str(spec_dir / "ema.ico"),
    upx=False,
)
exe_cli = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ema-cli",
    console=True,
    icon=str(spec_dir / "ema.ico"),
    upx=False,
)
coll = COLLECT(exe_gui, exe_cli, a.binaries, a.datas, name="Ema", upx=False)
