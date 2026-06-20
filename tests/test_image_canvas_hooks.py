"""Tests for the backward-compatible ImageCanvas hooks that the complex
dual-panel mode builds on: linked view, shared endpoints, projected load."""
from __future__ import annotations

import types

import numpy as np

from npyquick.core import limits
from npyquick.views.image import ImageCanvas


def _complex(h=10, w=10):
    re = np.arange(h * w).reshape(h, w).astype(np.float64)
    return (re + 1j * re).astype(np.complex128)


def test_apply_view_fires_set_view_silent():
    c = ImageCanvas()
    c.load(np.zeros((10, 20), dtype=np.float32))
    fired = []
    c.set_on_view_changed(lambda canv: fired.append(canv))

    c._reset_zoom()                 # routes through _apply_view
    assert fired == [c], "view change must fire on reset"

    fired.clear()
    c.set_view((0, 5), (5, 0))      # silent mirror sink
    assert fired == [], "set_view must not fire _on_view_changed"
    assert c.get_view() == ((0, 5), (5, 0))


def test_scroll_fires_view_changed():
    c = ImageCanvas()
    c.load(np.zeros((10, 10), dtype=np.float32))
    fired = []
    c.set_on_view_changed(lambda canv: fired.append(canv))
    ev = types.SimpleNamespace(inaxes=c._ax, step=1, xdata=5.0, ydata=5.0)
    c._on_scroll(ev)
    assert fired == [c]


def test_continuous_link_no_runaway():
    a = ImageCanvas()
    b = ImageCanvas()
    a.load(np.zeros((10, 10), dtype=np.float32))
    b.load(np.zeros((10, 10), dtype=np.float32))
    # Wire both directions, as ComplexImageView will.
    a.set_on_view_changed(lambda c: b.set_view(*c.get_view()))
    b.set_on_view_changed(lambda c: a.set_view(*c.get_view()))

    ev = types.SimpleNamespace(inaxes=a._ax, step=1, xdata=5.0, ydata=5.0)
    a._on_scroll(ev)                # must terminate (set_view is silent)
    assert b.get_view() == a.get_view()


def test_set_endpoints_is_silent_but_drag_fires():
    c = ImageCanvas()
    c.load(np.zeros((10, 10), dtype=np.float32))
    fired = []
    c.set_on_endpoints_changed(lambda canv: fired.append(canv))

    c.set_endpoints([[1.0, 1.0], [8.0, 8.0]])
    assert fired == [], "mirrored set_endpoints must not echo back"
    np.testing.assert_allclose(c.get_endpoints(), [[1.0, 1.0], [8.0, 8.0]])
    assert c.profile_data() is not None

    # Simulate a user drag of endpoint 0.
    c._dragging = 0
    c._pan_start = None
    ev = types.SimpleNamespace(inaxes=c._ax, xdata=3.0, ydata=4.0, x=0, y=0)
    c._on_motion(ev)
    assert fired == [c], "a user drag must fire _on_endpoints_changed"


def test_load_projector_strides_then_projects(monkeypatch):
    monkeypatch.setattr(limits, "IMAGE_MAX_PIXELS", 16)  # force stride on small array
    arr = _complex(10, 10)
    seen = {}

    def proj(sub):
        seen["dtype"] = sub.dtype
        seen["size"] = sub.size
        return np.real(sub)

    c = ImageCanvas()
    c.load(arr, projector=proj)
    assert np.issubdtype(seen["dtype"], np.complexfloating), "projector got complex"
    assert seen["size"] < arr.size, "projection must run on the strided (smaller) sub"
    assert not np.iscomplexobj(c._disp), "display must be real"
    assert np.iscomplexobj(c._data), "original complex array is retained"


def test_load_without_projector_unchanged_for_real():
    c = ImageCanvas()
    norm, down = c.load(np.arange(12, dtype=np.float32).reshape(3, 4))
    assert not np.iscomplexobj(c._disp)
    assert c.profile_data() is not None
