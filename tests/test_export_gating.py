"""Export must be disabled until data is actually loaded.

Covers the two cases where the current tab is disabled but exports were
otherwise reachable: app startup, and an .npz opened with no member selected.
"""
from __future__ import annotations

import numpy as np


def _export_plot_action_state(w):
    """Return (text, enabled) for the synthesised Export Plot menu entry."""
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
    main_window._copy_focused_plot()
    assert "No plot loaded" in main_window._sb.currentMessage()


def test_export_shortcut_hints_when_no_data(main_window):
    main_window._export_focused_plot()
    assert "No plot loaded" in main_window._sb.currentMessage()


def test_right_click_suppressed_when_no_data(main_window):
    # Mixin reads _has_data via duck typing on self.window().
    for v in main_window._views:
        canvas = getattr(v, "_canvas", None)
        if canvas is not None and hasattr(canvas, "_exports_allowed"):
            assert canvas._exports_allowed() is False


# ---------------------------------------------------------------------------
# After loading a .npy: gates open
# ---------------------------------------------------------------------------

def test_export_menu_enabled_after_loading_npy(main_window, write_npy):
    main_window.load_file(write_npy(np.arange(64, dtype=np.float32).reshape(8, 8)))

    assert main_window._has_data() is True
    main_window._rebuild_export_menu()
    acts = [a for a in main_window._export_actions if a.text()]
    enabled_action = [a for a in acts if a.isEnabled()]
    assert enabled_action, "Export Plot should be enabled once data is loaded"


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
