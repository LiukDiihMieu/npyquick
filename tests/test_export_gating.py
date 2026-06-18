"""Export must be disabled until data is actually loaded.

Covers the two cases where the current tab is disabled but exports were
otherwise reachable: app startup, and an .npz opened with no member selected.
"""
from __future__ import annotations

import numpy as np


def _export_plot_action_state(w):
    """Return (text, enabled) for the dynamic Export Plot menu entry."""
    w._rebuild_export_menu()
    acts = [a for a in w._export_actions if a.text()]
    assert len(acts) == 1, f"expected one Export Plot action, got {[a.text() for a in acts]}"
    return acts[0].text(), acts[0].isEnabled()


# ---------------------------------------------------------------------------
# Startup: nothing loaded
# ---------------------------------------------------------------------------

def test_has_data_false_at_startup(main_window):
    assert main_window._has_data() is False


def test_export_menu_disabled_at_startup(main_window):
    text, enabled = _export_plot_action_state(main_window)
    assert text == "Export Plot"
    assert enabled is False


def test_copy_shortcut_hints_when_no_data(main_window):
    main_window._copy_selected()
    assert "No plot loaded" in main_window._sb.currentMessage()


def test_export_shortcut_hints_when_no_data(main_window):
    main_window._export_selected()
    assert "No plot loaded" in main_window._sb.currentMessage()


def test_copy_hints_to_click_when_data_but_no_target(main_window, write_npy):
    main_window.load_file(write_npy(np.arange(64, dtype=np.float32).reshape(8, 8)))
    main_window._reset_selected_export_target()
    main_window._copy_selected()
    assert "Click a plot first" in main_window._sb.currentMessage()


def test_selected_actions_present_at_startup(main_window):
    # Always present/enabled so the shortcut fires and can show the hint.
    assert main_window._export_selected_action.text() == "Export Selected Plot…"
    assert main_window._copy_selected_action.text() == "Copy Selected Plot"


def test_selected_actions_grey_when_no_target_then_reenable(main_window):
    # Menu opening greys them out when nothing is selected...
    main_window._grey_selected_actions()
    assert main_window._export_selected_action.isEnabled() is False
    assert main_window._copy_selected_action.isEnabled() is False
    # ...and menu closing re-enables so the shortcut keeps firing (-> hint).
    main_window._enable_selected_actions()
    assert main_window._export_selected_action.isEnabled() is True
    assert main_window._copy_selected_action.isEnabled() is True


def test_selected_actions_stay_enabled_when_target_set(main_window, write_npy):
    main_window.load_file(write_npy(np.arange(64, dtype=np.float32).reshape(8, 8)))
    main_window.set_selected_export_target(main_window._image_view._canvas)
    main_window._grey_selected_actions()
    assert main_window._export_selected_action.isEnabled() is True
    assert main_window._copy_selected_action.isEnabled() is True


def test_right_click_suppressed_when_no_data(main_window):
    # Mixin reads _has_data via duck typing on self.window().
    for v in main_window._views:
        canvas = getattr(v, "_canvas", None)
        if canvas is not None and hasattr(canvas, "_exports_allowed"):
            assert canvas._exports_allowed() is False


# ---------------------------------------------------------------------------
# After loading a .npy: Export Plot gate opens
# ---------------------------------------------------------------------------

def test_export_menu_enabled_after_loading_npy(main_window, write_npy):
    main_window.load_file(write_npy(np.arange(64, dtype=np.float32).reshape(8, 8)))

    assert main_window._has_data() is True
    main_window._rebuild_export_menu()
    acts = [a for a in main_window._export_actions if a.text()]
    assert any(a.isEnabled() for a in acts), "Export Plot should be enabled once data is loaded"


def test_selected_target_drives_export(main_window, write_npy, monkeypatch):
    main_window.load_file(write_npy(np.arange(64, dtype=np.float32).reshape(8, 8)))
    canvas = main_window._image_view._canvas
    called = []
    monkeypatch.setattr(canvas, "export_figure", lambda: called.append(True))
    main_window.set_selected_export_target(canvas)
    main_window._export_selected()
    assert called == [True]


def test_selected_target_drives_copy(main_window, write_npy, monkeypatch):
    main_window.load_file(write_npy(np.arange(64, dtype=np.float32).reshape(8, 8)))
    canvas = main_window._image_view._canvas
    called = []
    monkeypatch.setattr(canvas, "copy_to_clipboard", lambda: called.append(True))
    main_window.set_selected_export_target(canvas)
    main_window._copy_selected()
    assert called == [True]


def test_export_targets_expose_public_export_figure(main_window, write_npy):
    main_window.load_file(write_npy(np.arange(64, dtype=np.float32).reshape(8, 8)))
    targets = main_window._image_view.export_targets()
    names = [n for n, _ in targets]
    assert names == ["Image", "Profile"]
    for _, fn in targets:
        assert fn.__name__ == "export_figure"


def test_set_on_selected_marks_export_target(main_window, write_npy):
    main_window.load_file(write_npy(np.arange(64, dtype=np.float32).reshape(8, 8)))
    canvas = main_window._image_view._canvas
    # set_on_selected is the public setter views use to wire the click callback;
    # invoking the stored callback must mark this canvas as the export target.
    canvas._on_selected(canvas)
    assert main_window._selected_export_target is canvas


# ---------------------------------------------------------------------------
# .npz with no member selected: same gating as startup
# ---------------------------------------------------------------------------

def test_export_menu_disabled_for_npz_until_member_selected(main_window, write_npz):
    main_window.load_file(write_npz(
        a=np.arange(9, dtype=np.float32).reshape(3, 3),
        b=np.arange(16, dtype=np.float32).reshape(4, 4),
    ))

    # Before selection: model.array is None, gates closed.
    assert main_window._has_data() is False
    text, enabled = _export_plot_action_state(main_window)
    assert (text, enabled) == ("Export Plot", False)

    # After selecting any member, gates open.
    main_window._model.select_array("a")
    main_window._refresh_views()
    assert main_window._has_data() is True
    main_window._rebuild_export_menu()
    acts = [a for a in main_window._export_actions if a.text()]
    assert any(a.isEnabled() for a in acts)
