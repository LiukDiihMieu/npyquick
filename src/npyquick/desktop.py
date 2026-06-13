# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import configparser
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


def _config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def _resolve_exec() -> str:
    # Inside an AppImage, $APPIMAGE is the stable absolute path of the .AppImage
    # file. argv[0]/which() would instead point into the ephemeral per-run mount
    # (/tmp/.mount_xxxx), which is gone once the app exits, so a baked Exec from
    # it would break. Prefer $APPIMAGE so file-manager double-click keeps working.
    appimage = os.environ.get("APPIMAGE")
    if appimage:
        return str(Path(appimage).resolve())

    # A bare `Exec=npyquick` relies on the file manager's session PATH, which
    # often lacks the conda/venv bin dir, so bake in the absolute path.
    # Prefer the launcher actually invoked (argv[0]) over a PATH lookup of the
    # app name: with several npyquick installs, which(APP_ID) could resolve to a
    # different one than the user ran. which() resolves a bare argv[0] via PATH
    # and accepts an explicit path as-is; resolve() makes it absolute.
    found = shutil.which(sys.argv[0]) or shutil.which(APP_ID)
    if found:
        return str(Path(found).resolve())

    raise RuntimeError(
        "Could not find a usable 'npyquick' executable. "
        "Install npyquick as a command-line script first."
    )


def _quote_exec(path: str) -> str:
    # freedesktop Exec quoting: wrap in double quotes (so spaces survive) and
    # backslash-escape the reserved characters " ` $ \ — otherwise a path like
    # /home/My Projects/bin/npyquick splits into two arguments.
    escaped = (
        path.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("`", "\\`")
        .replace("$", "\\$")
    )
    return f'"{escaped}"'


def _desktop_entry(exec_path: str) -> str:
    return f"""[Desktop Entry]
Type=Application
Name=npyquick
GenericName=NumPy Array Viewer
Comment=Quick viewer for NumPy .npy and .npz files
Exec={_quote_exec(exec_path)} %f
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
    <glob pattern="*.NPY" weight="100"/>
  </mime-type>
  <mime-type type="{MIME_NPZ}">
    <comment>NumPy compressed archive</comment>
    <sub-class-of type="application/zip"/>
    <glob pattern="*.npz" weight="100"/>
    <glob pattern="*.NPZ" weight="100"/>
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


def _remove_default_associations() -> None:
    # install() runs `xdg-mime default`, which records npyquick.desktop in
    # mimeapps.list. Removing only the .desktop/MIME files would leave that
    # dangling, so strip our entries here too.
    path = _config_home() / "mimeapps.list"
    if not path.exists():
        return
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # preserve case of MIME-type keys
    try:
        parser.read(path, encoding="utf-8")
    except configparser.Error:
        return

    changed = False
    for section in ("Default Applications", "Added Associations"):
        if not parser.has_section(section):
            continue
        for mime in (MIME_NPY, MIME_NPZ):
            if not parser.has_option(section, mime):
                continue
            entries = [
                e for e in parser.get(section, mime).split(";")
                if e and e != DESKTOP_FILE
            ]
            if entries:
                parser.set(section, mime, ";".join(entries) + ";")
            else:
                parser.remove_option(section, mime)
            changed = True

    if changed:
        with path.open("w", encoding="utf-8") as f:
            parser.write(f, space_around_delimiters=False)


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

    desktop_path.write_text(_desktop_entry(_resolve_exec()), encoding="utf-8")
    mime_path.write_text(_mime_xml(), encoding="utf-8")

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

    _remove_default_associations()

    _run(["update-mime-database", str(data / "mime")])
    _run(["update-desktop-database", str(desktop_path.parent)])
    _run(["gtk-update-icon-cache", "-f", "-t", str(data / "icons" / "hicolor")])

    if removed:
        return "Removed npyquick desktop integration:\n  " + "\n  ".join(removed)
    return "No npyquick desktop integration found."
