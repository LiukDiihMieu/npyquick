"""App-level workflows that span the load -> refresh -> menu chain.

These complement test_npz_picker.py (picker UI) and test_export_gating.py
(empty-state gating) by exercising what happens when a load fails and what
happens when the array type changes the shape of the Export Plot menu.
"""
from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# load_file() error handling: a bad file must not clobber prior state.
# ---------------------------------------------------------------------------

def test_corrupt_npy_at_startup_reports_error_and_keeps_no_data(
    main_window, tmp_path,
):
    bad = tmp_path / "bad.npy"
    bad.write_bytes(b"not a valid numpy file")

    main_window.load_file(str(bad))

    assert "Error" in main_window._sb.currentMessage()
    assert main_window._has_data() is False


def test_corrupt_npy_load_preserves_previously_loaded_array(
    main_window, write_npy, tmp_path,
):
    """A failed load shows an error and leaves the prior array in place."""
    good_path = write_npy(np.arange(20, dtype=np.float32).reshape(4, 5))
    main_window.load_file(good_path)
    prior = main_window._model.array.copy()
    assert main_window._has_data() is True

    bad = tmp_path / "bad.npy"
    bad.write_bytes(b"definitely not a numpy file")
    main_window.load_file(str(bad))

    assert "Error" in main_window._sb.currentMessage()
    np.testing.assert_array_equal(main_window._model.array, prior)


# ---------------------------------------------------------------------------
# Export Plot menu shape per view type, plus correct rebuild on transitions.
# ---------------------------------------------------------------------------

def _export_actions_with_label(main_window):
    return [a for a in main_window._export_actions if a.text()]


def test_export_menu_uses_submenu_for_2d_image(main_window, write_npy):
    main_window.load_file(write_npy(np.zeros((8, 8), dtype=np.float32)))
    main_window._rebuild_export_menu()

    with_menus = [a for a in main_window._export_actions if a.menu() is not None]
    assert len(with_menus) == 1
    child_names = {a.text().rstrip("…") for a in with_menus[0].menu().actions()}
    assert child_names == {"Image", "Profile"}


def test_export_menu_uses_single_action_for_1d_lineplot(main_window, write_npy):
    main_window.load_file(write_npy(np.arange(20, dtype=np.float32)))
    main_window._rebuild_export_menu()

    labelled = _export_actions_with_label(main_window)
    assert any(a.text() == "Export Plot…" for a in labelled)
    assert all(a.menu() is None for a in main_window._export_actions)


def test_export_menu_rebuilds_when_array_type_changes(main_window, write_npy):
    """2D -> 1D -> 2D must produce submenu -> single -> submenu."""
    img = np.zeros((8, 8), dtype=np.float32)
    line = np.arange(20, dtype=np.float32)

    main_window.load_file(write_npy(img, name="img1.npy"))
    main_window._rebuild_export_menu()
    assert any(a.menu() is not None for a in main_window._export_actions)

    main_window.load_file(write_npy(line, name="line.npy"))
    main_window._rebuild_export_menu()
    assert any(a.text() == "Export Plot…" for a in _export_actions_with_label(main_window))
    assert all(a.menu() is None for a in main_window._export_actions)

    main_window.load_file(write_npy(img, name="img2.npy"))
    main_window._rebuild_export_menu()
    assert any(a.menu() is not None for a in main_window._export_actions)


# ---------------------------------------------------------------------------
# Reload action — enabled state and success/failure status messages.
# ---------------------------------------------------------------------------

def test_reload_action_disabled_before_first_load(main_window):
    assert main_window._reload_action.isEnabled() is False


def test_reload_action_enabled_after_load(main_window, write_npy):
    main_window.load_file(write_npy(np.arange(10, dtype=np.float32)))
    assert main_window._reload_action.isEnabled() is True


def test_reload_success_shows_reloaded_message(main_window, write_npy):
    path = write_npy(np.arange(10, dtype=np.float32))
    main_window.load_file(path)
    main_window._reload_file()
    assert main_window._sb.currentMessage() == "File reloaded"


def test_reload_failure_preserves_error_message(main_window, write_npy, tmp_path):
    """A failed reload must not overwrite the error with 'File reloaded'."""
    main_window.load_file(write_npy(np.arange(10, dtype=np.float32)))

    # Overwrite the file on disk with garbage so the next load fails.
    bad = tmp_path / "gone.npy"
    bad.write_bytes(b"corrupted")
    main_window._current_path = str(bad)

    main_window._reload_file()

    assert "Error" in main_window._sb.currentMessage()
    assert "reloaded" not in main_window._sb.currentMessage()
