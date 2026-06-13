"""Linux desktop integration: file generation and install/uninstall.

These exercise npyquick.desktop without touching the real system: the external
update-mime-database / update-desktop-database / xdg-mime calls are stubbed and
XDG_DATA_HOME is redirected into a tmp dir, so install() and uninstall() only
read and write under the sandbox.
"""
from __future__ import annotations

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
    assert exec_line == "Exec=/usr/bin/npyquick %f"
    assert "%F" not in entry


def test_desktop_entry_declares_both_mime_types():
    entry = desktop._desktop_entry("/usr/bin/npyquick")
    assert f"MimeType={desktop.MIME_NPY};{desktop.MIME_NPZ};" in entry


def test_mime_xml_subclasses_zip_for_npz():
    xml = desktop._mime_xml()
    assert '<sub-class-of type="application/zip"/>' in xml
    assert '<glob pattern="*.npz" weight="100"/>' in xml
    assert '<glob pattern="*.npy" weight="100"/>' in xml


# ---------------------------------------------------------------------------
# install() / uninstall() filesystem effects, with external tools stubbed.
# ---------------------------------------------------------------------------

@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
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
    assert "Exec=/usr/bin/npyquick %f" in desktop_path.read_text()


def test_uninstall_removes_installed_files(sandbox):
    desktop.install()
    desktop.uninstall()
    for p in _expected_paths(sandbox):
        assert not p.exists()


def test_uninstall_is_safe_when_nothing_installed(sandbox):
    msg = desktop.uninstall()
    assert "No npyquick desktop integration found." in msg
