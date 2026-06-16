from __future__ import annotations

import matplotlib as mpl

from npyquick.app import _apply_canvas_theme


def test_apply_canvas_theme_noop_when_not_dark(qapp):
    # Offscreen reports ColorScheme.Unknown, so the canvas must stay default.
    before = mpl.rcParams["figure.facecolor"]
    _apply_canvas_theme()
    assert mpl.rcParams["figure.facecolor"] == before
