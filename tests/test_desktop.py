"""Linux desktop integration: file generation and install/uninstall.

These exercise npyquick.desktop without touching the real system: the external
update-mime-database / update-desktop-database / xdg-mime calls are stubbed and
XDG_DATA_HOME is redirected into a tmp dir, so install() and uninstall() only
read and write under the sandbox.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from npyquick import desktop


# ---------------------------------------------------------------------------
# Generated file content — guards the two correctness points from the plan:
# Exec must use %f (single file, matching the CLI) and .npz must declare
# sub-class-of application/zip (so the *.npz glob beats zip content-sniffing).
# ---------------------------------------------------------------------------

def test_desktop_entry_uses_single_file_placeholder():
    entry = desktop._desktop_entry("/usr/bin/npyquick")
    exec_line = next(ln for ln in entry.splitlines() if ln.startswith("Exec="))
    assert exec_line == 'Exec="/usr/bin/npyquick" %f'
    assert "%F" not in entry


def test_desktop_entry_quotes_path_with_spaces():
    entry = desktop._desktop_entry("/home/My Projects/bin/npyquick")
    exec_line = next(ln for ln in entry.splitlines() if ln.startswith("Exec="))
    assert exec_line == 'Exec="/home/My Projects/bin/npyquick" %f'


def test_resolve_exec_prefers_invoked_launcher_over_path_app(monkeypatch):
    # argv[0] is a specific install; a different npyquick sits on PATH.
    monkeypatch.delenv("APPIMAGE", raising=False)
    monkeypatch.setattr(desktop.sys, "argv", ["/opt/venv/bin/npyquick", "--install-desktop"])
    monkeypatch.setattr(
        desktop.shutil, "which",
        lambda c: c if c == "/opt/venv/bin/npyquick" else "/usr/bin/npyquick",
    )
    assert desktop._resolve_exec() == "/opt/venv/bin/npyquick"


def test_resolve_exec_is_always_absolute(monkeypatch, tmp_path):
    monkeypatch.delenv("APPIMAGE", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(desktop.sys, "argv", ["./npyquick"])
    monkeypatch.setattr(desktop.shutil, "which", lambda c: c if c == "./npyquick" else None)
    result = desktop._resolve_exec()
    assert os.path.isabs(result)


def test_resolve_exec_raises_when_no_executable(monkeypatch):
    monkeypatch.delenv("APPIMAGE", raising=False)
    monkeypatch.setattr(desktop.sys, "argv", ["-c"])
    monkeypatch.setattr(desktop.shutil, "which", lambda c: None)
    with pytest.raises(RuntimeError, match="npyquick"):
        desktop._resolve_exec()


def test_resolve_exec_prefers_appimage_path(monkeypatch):
    # Running from an AppImage: $APPIMAGE is the stable .AppImage path and must
    # win over argv[0], which points into the ephemeral /tmp mount.
    monkeypatch.setenv("APPIMAGE", "/home/me/Apps/npyquick-x86_64.AppImage")
    monkeypatch.setattr(desktop.sys, "argv", ["/tmp/.mount_npyqXX/usr/bin/npyquick"])
    monkeypatch.setattr(desktop.shutil, "which", lambda c: "/tmp/.mount_npyqXX/usr/bin/npyquick")
    assert desktop._resolve_exec() == "/home/me/Apps/npyquick-x86_64.AppImage"


def test_resolve_exec_ignores_appimage_when_unset(monkeypatch):
    # A plain pip install has no $APPIMAGE; behaviour falls back to argv[0].
    monkeypatch.delenv("APPIMAGE", raising=False)
    monkeypatch.setattr(desktop.sys, "argv", ["/opt/venv/bin/npyquick"])
    monkeypatch.setattr(desktop.shutil, "which", lambda c: c)
    assert desktop._resolve_exec() == "/opt/venv/bin/npyquick"


def test_desktop_entry_declares_both_mime_types():
    entry = desktop._desktop_entry("/usr/bin/npyquick")
    assert f"MimeType={desktop.MIME_NPY};{desktop.MIME_NPZ};" in entry


def test_desktop_entry_icon_uses_rdns_id():
    # Icon must match the installed icon basename (ICON_FILE) and the AppStream
    # component id, so the desktop pairs with the right icon.
    entry = desktop._desktop_entry("/usr/bin/npyquick")
    assert f"Icon={desktop.APP_RDNS}" in entry
    assert desktop.ICON_FILE == f"{desktop.APP_RDNS}.svg"
    assert desktop.DESKTOP_FILE == f"{desktop.APP_RDNS}.desktop"


def test_mime_xml_subclasses_zip_for_npz():
    xml = desktop._mime_xml()
    assert '<sub-class-of type="application/zip"/>' in xml
    assert '<glob pattern="*.npz" weight="100"/>' in xml
    assert '<glob pattern="*.npy" weight="100"/>' in xml


def test_mime_xml_includes_uppercase_globs():
    xml = desktop._mime_xml()
    assert '<glob pattern="*.NPY" weight="100"/>' in xml
    assert '<glob pattern="*.NPZ" weight="100"/>' in xml


def test_mime_xml_matches_mime_constants():
    # The XML now lives in a resource file, but the MIME_NPY / MIME_NPZ
    # constants are still used for xdg-mime and mimeapps.list handling. Guard
    # against the two drifting apart.
    xml = desktop._mime_xml()
    assert f'type="{desktop.MIME_NPY}"' in xml
    assert f'type="{desktop.MIME_NPZ}"' in xml


# ---------------------------------------------------------------------------
# install() / uninstall() filesystem effects, with external tools stubbed.
# ---------------------------------------------------------------------------

@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    # Redirect both XDG homes into the temp dir so install/uninstall never
    # touch the developer's real ~/.local/share or ~/.config/mimeapps.list.
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(desktop, "_run", lambda cmd: None)
    monkeypatch.setattr(desktop, "_resolve_exec", lambda: "/usr/bin/npyquick")
    return tmp_path


def _expected_paths(data: Path) -> tuple[Path, Path, Path]:
    return (
        data / "applications" / desktop.DESKTOP_FILE,
        data / "mime" / "packages" / desktop.MIME_FILE,
        data / "icons" / "hicolor" / "scalable" / "apps" / desktop.ICON_FILE,
    )


def test_install_writes_all_three_files(sandbox):
    desktop.install()
    desktop_path, mime_path, icon_path = _expected_paths(sandbox)
    assert desktop_path.is_file()
    assert mime_path.is_file()
    assert icon_path.is_file()
    # icon was copied from package resources, not left empty
    assert icon_path.stat().st_size > 0


def test_install_writes_resolved_exec_path(sandbox):
    desktop.install()
    desktop_path, _, _ = _expected_paths(sandbox)
    assert 'Exec="/usr/bin/npyquick" %f' in desktop_path.read_text()


def test_uninstall_removes_installed_files(sandbox):
    desktop.install()
    desktop.uninstall()
    for p in _expected_paths(sandbox):
        assert not p.exists()


def test_uninstall_is_safe_when_nothing_installed(sandbox):
    msg = desktop.uninstall()
    assert "No npyquick desktop integration found." in msg


def test_uninstall_strips_default_associations(sandbox, tmp_path):
    config = tmp_path / "config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "mimeapps.list").write_text(
        "[Default Applications]\n"
        f"application/x-npy={desktop.DESKTOP_FILE};\n"
        f"application/x-npz={desktop.DESKTOP_FILE};\n"
        "text/plain=gedit.desktop;\n"
    )
    desktop.install()
    desktop.uninstall()
    content = (config / "mimeapps.list").read_text()
    assert desktop.DESKTOP_FILE not in content      # our entries removed
    assert "text/plain=gedit.desktop;" in content   # unrelated entry preserved


def test_uninstall_preserves_other_handlers_in_list(sandbox, tmp_path):
    config = tmp_path / "config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "mimeapps.list").write_text(
        "[Default Applications]\n"
        f"application/x-npy={desktop.DESKTOP_FILE};other.desktop;\n"
    )
    desktop.uninstall()
    content = (config / "mimeapps.list").read_text()
    assert desktop.DESKTOP_FILE not in content
    assert "other.desktop;" in content
