# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

APP_ID = "npyquick"
DESKTOP_FILE = "npyquick.desktop"
MIME_FILE = "npyquick.xml"
ICON_FILE = "npyquick.svg"
MIME_NPY = "application/x-npy"
MIME_NPZ = "application/x-npz"


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def _resolve_exec() -> str:
    # A bare `Exec=npyquick` relies on the file manager's session PATH, which
    # often lacks the conda/venv bin dir. Bake in the absolute launcher path.
    return shutil.which(APP_ID) or os.path.realpath(sys.argv[0])


def _desktop_entry(exec_path: str) -> str:
    return f"""[Desktop Entry]
Type=Application
Name=npyquick
GenericName=NumPy Array Viewer
Comment=Quick viewer for NumPy .npy and .npz files
Exec={exec_path} %f
Icon={APP_ID}
Terminal=false
Categories=Science;Utility;
MimeType={MIME_NPY};{MIME_NPZ};
Keywords=numpy;npy;npz;array;viewer;
StartupNotify=true
"""


def _mime_xml() -> str:
    # .npz is a zip internally; without sub-class-of the system's content
    # sniffing reports application/zip and the *.npz glob loses. Declaring the
    # subclass lets the more specific glob win deterministically.
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="{MIME_NPY}">
    <comment>NumPy array</comment>
    <glob pattern="*.npy" weight="100"/>
  </mime-type>
  <mime-type type="{MIME_NPZ}">
    <comment>NumPy compressed archive</comment>
    <sub-class-of type="application/zip"/>
    <glob pattern="*.npz" weight="100"/>
  </mime-type>
</mime-info>
"""


def _run(cmd: list[str]) -> None:
    exe = shutil.which(cmd[0])
    if exe is None:
        return
    try:
        subprocess.run([exe, *cmd[1:]], check=False, capture_output=True)
    except OSError:
        pass


def _paths(data: Path) -> tuple[Path, Path, Path]:
    return (
        data / "applications" / DESKTOP_FILE,
        data / "mime" / "packages" / MIME_FILE,
        data / "icons" / "hicolor" / "scalable" / "apps" / ICON_FILE,
    )


def install() -> str:
    data = _data_home()
    desktop_path, mime_path, icon_path = _paths(data)
    for p in (desktop_path, mime_path, icon_path):
        p.parent.mkdir(parents=True, exist_ok=True)

    desktop_path.write_text(_desktop_entry(_resolve_exec()))
    mime_path.write_text(_mime_xml())

    icon_src = files(APP_ID) / "resources" / "icon.svg"
    try:
        icon_path.write_bytes(icon_src.read_bytes())
    except (FileNotFoundError, OSError):
        pass  # icon is cosmetic; the association still works without it

    _run(["update-mime-database", str(data / "mime")])
    _run(["update-desktop-database", str(desktop_path.parent)])
    # Refresh the icon-theme cache; a stale cache hides the freshly-added SVG.
    _run(["gtk-update-icon-cache", "-f", "-t", str(data / "icons" / "hicolor")])
    _run(["xdg-mime", "default", DESKTOP_FILE, MIME_NPY])
    _run(["xdg-mime", "default", DESKTOP_FILE, MIME_NPZ])

    return (
        "Installed npyquick desktop integration:\n"
        f"  {desktop_path}\n  {mime_path}\n  {icon_path}\n"
        "Test with: xdg-open file.npy"
    )


def uninstall() -> str:
    data = _data_home()
    desktop_path, mime_path, icon_path = _paths(data)
    removed = []
    for p in (desktop_path, mime_path, icon_path):
        if p.exists():
            p.unlink()
            removed.append(str(p))

    _run(["update-mime-database", str(data / "mime")])
    _run(["update-desktop-database", str(desktop_path.parent)])
    _run(["gtk-update-icon-cache", "-f", "-t", str(data / "icons" / "hicolor")])

    if removed:
        return "Removed npyquick desktop integration:\n  " + "\n  ".join(removed)
    return "No npyquick desktop integration found."
