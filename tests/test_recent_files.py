"""Tests for the File › Open Recent menu backed by QSettings."""
from __future__ import annotations

import os

import numpy as np
import pytest
from PySide6.QtCore import QSettings


@pytest.fixture(autouse=True)
def clean_recent():
    """QSettings persists across tests (and runs) in the Qt test sandbox, so
    pin a known-empty starting state and leave none behind."""
    QSettings("npyquick", "npyquick").setValue("recent_files", [])
    yield
    QSettings("npyquick", "npyquick").setValue("recent_files", [])


def _menu_actions(main_window):
    main_window._rebuild_recent_menu()
    return main_window._recent_menu.actions()


def test_empty_recent_shows_disabled_placeholder(main_window):
    actions = _menu_actions(main_window)
    assert len(actions) == 1
    assert actions[0].text() == "(no recent files)"
    assert not actions[0].isEnabled()


def test_load_records_most_recent_first(main_window, write_npy):
    a = write_npy(np.zeros((4, 4)), name="a.npy")
    b = write_npy(np.zeros((4, 4)), name="b.npy")
    main_window.load_file(a)
    main_window.load_file(b)
    assert main_window._recent_files() == [os.path.abspath(b), os.path.abspath(a)]


def test_reopening_moves_entry_to_front_without_duplicate(main_window, write_npy):
    a = write_npy(np.zeros((4, 4)), name="a.npy")
    b = write_npy(np.zeros((4, 4)), name="b.npy")
    main_window.load_file(a)
    main_window.load_file(b)
    main_window.load_file(a)
    assert main_window._recent_files() == [os.path.abspath(a), os.path.abspath(b)]


def test_recent_list_is_capped(main_window, write_npy):
    for i in range(10):
        main_window.load_file(write_npy(np.zeros((2, 2)), name=f"f{i}.npy"))
    recent = main_window._recent_files()
    assert len(recent) == main_window._RECENT_MAX
    assert recent[0].endswith("f9.npy")


def test_failed_load_is_not_recorded(main_window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok
    )
    bad = tmp_path / "bad.npy"
    bad.write_bytes(b"not numpy")
    main_window.load_file(str(bad))
    assert main_window._recent_files() == []


def test_menu_entry_loads_the_file(main_window, write_npy):
    path = write_npy(np.arange(6, dtype=np.float32).reshape(2, 3), name="pick.npy")
    main_window.load_file(path)
    main_window._model.array = None  # forget the load, keep the recent entry

    entry = _menu_actions(main_window)[0]
    entry.trigger()
    assert main_window._has_data()
    assert main_window.windowTitle().endswith("pick.npy")


def test_home_paths_are_abbreviated_with_tilde(main_window, write_npy, monkeypatch):
    path = write_npy(np.zeros((2, 2)), name="deep.npy")
    monkeypatch.setenv("HOME", os.path.dirname(path))  # treat tmp_path as home
    main_window.load_file(path)
    entry = _menu_actions(main_window)[0]
    assert entry.text() == "~/deep.npy"
    assert entry.toolTip() == os.path.abspath(path)


def test_ampersand_in_name_is_escaped_for_the_menu_label(main_window, write_npy):
    # "&" is the menu mnemonic marker; the visible label must escape it while
    # the tooltip and the loadable path keep the literal name.
    path = write_npy(np.zeros((2, 2)), name="Q&A.npy")
    main_window.load_file(path)
    entry = _menu_actions(main_window)[0]
    assert entry.text().endswith("Q&&A.npy")   # escaped for display
    assert entry.iconText().endswith("Q&A.npy")  # renders with a literal &
    assert entry.toolTip() == os.path.abspath(path)


def test_missing_file_is_greyed_not_pruned(main_window, write_npy):
    path = write_npy(np.zeros((2, 2)), name="gone.npy")
    main_window.load_file(path)
    os.remove(path)
    entry = _menu_actions(main_window)[0]
    assert not entry.isEnabled()
    assert main_window._recent_files() == [os.path.abspath(path)]


def test_greyed_entry_explains_snap_sandbox(main_window, write_npy, monkeypatch):
    path = write_npy(np.zeros((2, 2)), name="outside.npy")
    main_window.load_file(path)
    os.remove(path)
    monkeypatch.setenv("SNAP", "/snap/npyquick/x1")
    entry = _menu_actions(main_window)[0]
    assert not entry.isEnabled()
    assert "File > Open" in entry.toolTip()


def test_portal_document_paths_are_not_recorded(main_window):
    main_window._add_recent_file("/run/user/1000/doc/abc123/data.npy")
    assert main_window._recent_files() == []


def test_clear_recent_empties_settings_and_menu(main_window, write_npy):
    main_window.load_file(write_npy(np.zeros((2, 2)), name="x.npy"))
    main_window._clear_recent()
    assert main_window._recent_files() == []
    actions = _menu_actions(main_window)
    assert actions[0].text() == "(no recent files)"


def test_single_entry_reads_back_as_list(main_window):
    # INI backend round-trips a 1-element list as a plain string.
    QSettings("npyquick", "npyquick").setValue("recent_files", "/tmp/only.npy")
    assert main_window._recent_files() == ["/tmp/only.npy"]


def test_empty_stored_list_reads_back_as_empty(main_window):
    # An INI-stored empty list reads back as None; without normalization the
    # next load_file (or menu rebuild) would crash on list(None). This is the
    # real "Clear Recent, then open a file" path.
    QSettings("npyquick", "npyquick").setValue("recent_files", [])
    assert main_window._recent_files() == []
    main_window._add_recent_file("/tmp/after_clear.npy")  # must not raise
    assert main_window._recent_files() == ["/tmp/after_clear.npy"]
