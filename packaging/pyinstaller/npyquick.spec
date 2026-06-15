# -*- mode: python ; coding: utf-8 -*-
# PyInstaller onedir spec for npyquick, shared across platforms: wrapped into an
# AppImage by packaging/appimage, and into a Windows installer by packaging/windows.
import os

from PyInstaller.utils.hooks import collect_data_files

entry = os.path.join(SPECPATH, "npyquick_entry.py")

# Windows: embed the app icon in the .exe if the asset is present. Harmless
# elsewhere — PyInstaller ignores `icon` for the Linux ELF, and None is allowed.
_icon = os.path.join(SPECPATH, "..", "windows", "npyquick.ico")
icon = _icon if os.path.exists(_icon) else None

# matplotlib's Qt backend is imported dynamically, so PyInstaller can't see it
# by static analysis; name it explicitly. numpy / scipy / PySide6 are covered by
# PyInstaller's bundled hooks.
hiddenimports = ["matplotlib.backends.backend_qtagg"]

# Bundle npyquick's own package data (icon + MIME XML) so `--install-desktop`
# works when run from the AppImage. Filter to the real assets — resources/ may
# contain a stray .ipynb_checkpoints dir locally.
datas = collect_data_files("matplotlib")
datas += collect_data_files("npyquick", includes=["resources/*.svg", "resources/*.xml"])

a = Analysis(
    [entry],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="npyquick",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="npyquick",
)
