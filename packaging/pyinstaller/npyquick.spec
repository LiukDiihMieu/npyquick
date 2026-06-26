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

# matplotlib's backends are imported dynamically, so PyInstaller can't see them
# by static analysis; name them explicitly. backend_qtagg drives the on-screen
# canvas (and PNG export); backend_svg / backend_pdf are loaded lazily by savefig
# only when those formats are requested, so the frozen build would otherwise ship
# without them and SVG/PDF export would fail with only PNG working (issue #33).
# numpy / scipy / PySide6 are covered by PyInstaller's bundled hooks.
hiddenimports = [
    "matplotlib.backends.backend_qtagg",
    "matplotlib.backends.backend_svg",
    "matplotlib.backends.backend_pdf",
]

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

# AppImage/Linux: GLib and its GIO/GObject siblings must come from the host, not
# the bundle. Qt and GTK read desktop settings (e.g. the GNOME dark-mode
# color-scheme, issue #19) through GIO modules such as dconf that are loaded from
# the host at runtime and built against the host GLib. A bundled GLib shadows the
# host one; on a host newer than the build machine those modules then fail to
# resolve their symbols, GSettings falls back to defaults, and dark mode reads as
# light — exactly the case AppImage's excludelist warns about. Dropping the GLib
# family lets the host provide it. Safe because the build runs on the oldest
# supported system (Ubuntu 22.04 / GLib 2.72), so the bundled Qt/GTK need no
# newer GLib than any supported host already ships. These names never match on
# Windows, so the filter is a no-op there.
_host_provided = (
    "libglib-2.0.so",
    "libgio-2.0.so",
    "libgobject-2.0.so",
    "libgmodule-2.0.so",
    "libgthread-2.0.so",
)
a.binaries = [
    b for b in a.binaries
    if not os.path.basename(b[0]).startswith(_host_provided)
]

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
