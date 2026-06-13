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
    monkeypatch.setattr(desktop.sys, "argv", ["/opt/venv/bin/npyquick", "--install-desktop"])
    monkeypatch.setattr(
        desktop.shutil, "which",
        lambda c: c if c == "/opt/venv/bin/npyquick" else "/usr/bin/npyquick",
    )
    assert desktop._resolve_exec() == "/opt/venv/bin/npyquick"


def test_resolve_exec_is_always_absolute(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(desktop.sys, "argv", ["./npyquick"])
    monkeypatch.setattr(desktop.shutil, "which", lambda c: c if c == "./npyquick" else None)
    result = desktop._resolve_exec()
    assert os.path.isabs(result)


def test_resolve_exec_raises_when_no_executable(monkeypatch):
    monkeypatch.setattr(desktop.sys, "argv", ["-c"])
    monkeypatch.setattr(desktop.shutil, "which", lambda c: None)
    with pytest.raises(RuntimeError, match="npyquick"):
        desktop._resolve_exec()


def test_desktop_entry_declares_both_mime_types():
    entry = desktop._desktop_entry("/usr/bin/npyquick")
    assert f"MimeType={desktop.MIME_NPY};{desktop.MIME_NPZ};" in entry


def test_mime_xml_subclasses_zip_for_npz():
    xml = desktop._mime_xml()
    assert '<sub-class-of type="application/zip"/>' in xml
    assert '<glob pattern="*.npz" weight="100"/>' in xml
    assert '<glob pattern="*.npy" weight="100"/>' in xml


def test_mime_xml_includes_uppercase_globs():
    xml = desktop._mime_xml()
    assert '<glob pattern="*.NPY" weight="100"/>' in xml
    assert '<glob pattern="*.NPZ" weight="100"/>' in xml


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
        data / "applications" / "npyquick.desktop",
        data / "mime" / "packages" / "npyquick.xml",
        data / "icons" / "hicolor" / "scalable" / "apps" / "npyquick.svg",
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
        "application/x-npy=npyquick.desktop;\n"
        "application/x-npz=npyquick.desktop;\n"
        "text/plain=gedit.desktop;\n"
    )
    desktop.install()
    desktop.uninstall()
    content = (config / "mimeapps.list").read_text()
    assert "npyquick.desktop" not in content       # our entries removed
    assert "text/plain=gedit.desktop;" in content   # unrelated entry preserved


def test_uninstall_preserves_other_handlers_in_list(sandbox, tmp_path):
    config = tmp_path / "config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "mimeapps.list").write_text(
        "[Default Applications]\n"
        "application/x-npy=npyquick.desktop;other.desktop;\n"
    )
    desktop.uninstall()
    content = (config / "mimeapps.list").read_text()
    assert "npyquick.desktop" not in content
    assert "other.desktop;" in content
