"""Tests for the gradient swatch icons in the View › Colormap menu."""
from __future__ import annotations

from npyquick.app import _colormap_icon


def _edge_lightness(icon, size=16):
    """Return (left, right) grayscale lightness of the icon's middle row."""
    img = icon.pixmap(size, size).toImage()
    left = img.pixelColor(0, size // 2)
    right = img.pixelColor(size - 1, size // 2)
    return left.lightness(), right.lightness()


def test_gray_swatch_runs_dark_to_light(qapp):
    icon = _colormap_icon("gray", 16, 1.0)
    assert not icon.isNull()
    left, right = _edge_lightness(icon)
    assert left < right


def test_reversed_swatch_runs_light_to_dark(qapp):
    left, right = _edge_lightness(_colormap_icon("gray_r", 16, 1.0))
    assert left > right


def test_all_colormap_actions_have_icons(main_window):
    assert len(main_window._cmap_actions) == 11
    for action, _base in main_window._cmap_actions:
        assert not action.icon().isNull()


def test_reverse_toggle_flips_the_swatches(main_window):
    gray_action = next(a for a, base in main_window._cmap_actions if base == "gray")
    # Pin a known state first: colormap_reverse persists in QSettings, so the
    # window may have been constructed with reverse already on.
    main_window._set_colormap_reverse(False)
    left_before, _ = _edge_lightness(gray_action.icon())
    main_window._set_colormap_reverse(True)
    left_after, _ = _edge_lightness(gray_action.icon())
    main_window._set_colormap_reverse(False)
    assert left_before < left_after, "gray swatch must start light once reversed"
