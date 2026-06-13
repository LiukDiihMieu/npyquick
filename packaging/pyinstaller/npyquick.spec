# -*- mode: python ; coding: utf-8 -*-
# PyInstaller onedir spec for npyquick. Built into an AppImage by packaging/appimage.
import os

from PyInstaller.utils.hooks import collect_data_files

entry = os.path.join(SPECPATH, "npyquick_entry.py")

# matplotlib's Qt backend is imported dynamically, so PyInstaller can't see it
# by static analysis; name it explicitly. numpy / scipy / PySide6 are covered by
# PyInstaller's bundled hooks.
hiddenimports = ["matplotlib.backends.backend_qtagg"]

a = Analysis(
    [entry],
    pathex=[],
    binaries=[],
    datas=collect_data_files("matplotlib"),
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="npyquick",
)
