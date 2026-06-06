"""LineplotView / LineplotCanvas tests."""
from __future__ import annotations

import numpy as np
import pytest

from npyquick.core import limits
from npyquick.views.lineplot import LineplotCanvas, LineplotView


def _view() -> LineplotView:
    return LineplotView()


# ---------------------------------------------------------------------------
# can_handle
# ---------------------------------------------------------------------------

def test_can_handle_1d_real():
    assert LineplotView.can_handle(np.zeros(10, dtype=np.float32)) is True


def test_can_handle_2d_real():
    assert LineplotView.can_handle(np.zeros((2, 10), dtype=np.float32)) is True


def test_can_handle_2d_2x2_rejected():
    # (2, 2) is ambiguous — treated as a 2×2 matrix, not an [x, y] pair
    assert LineplotView.can_handle(np.zeros((2, 2), dtype=np.float32)) is False


def test_can_handle_2d_nxn_rejected():
    assert LineplotView.can_handle(np.zeros((10, 10), dtype=np.float32)) is False


def test_can_handle_complex_rejected():
    assert LineplotView.can_handle(np.zeros(10, dtype=np.complex64)) is False


def test_can_handle_empty_rejected():
    assert LineplotView.can_handle(np.zeros(0, dtype=np.float32)) is False


# ---------------------------------------------------------------------------
# set_data — 1D mode
# ---------------------------------------------------------------------------

def test_set_data_1d_mode():
    v = _view()
    arr = np.linspace(0, 1, 50, dtype=np.float32)
    v.set_data(arr)
    assert v._canvas._mode == "1d"
    assert v._canvas._data is arr
    assert np.issubdtype(v._canvas._disp.dtype, np.floating)
    assert v._canvas._stride == 1


def test_set_data_xy_mode():
    v = _view()
    x = np.linspace(400, 700, 50)     # wavelengths
    y = np.random.default_rng(0).random(50)
    arr = np.stack([x, y])             # shape (2, 50)
    v.set_data(arr)
    assert v._canvas._mode == "xy"
    assert v._canvas._data is arr
    # x_disp should be derived from row 0
    np.testing.assert_allclose(v._canvas._x_disp, x)  # pixel_size == 1.0


# ---------------------------------------------------------------------------
# Large-array downsampling
# ---------------------------------------------------------------------------

def test_set_data_downsamples_large(monkeypatch):
    monkeypatch.setattr(limits, "HIST_MAX_SAMPLES", 16)
    v = _view()
    arr = np.ones(100, dtype=np.float32)
    v.set_data(arr)
    assert v._canvas._stride > 1
    assert v._canvas._disp.size < 100
    assert v._canvas._data.size == 100  # full-res retained


# ---------------------------------------------------------------------------
# pixel_size
# ---------------------------------------------------------------------------

def test_set_pixel_size_before_load():
    v = _view()
    v.set_pixel_size(2.0, "μm")          # should not crash
    assert v._canvas._pixel_size == 2.0
    assert v._canvas._unit == "μm"


def test_set_pixel_size_after_load():
    v = _view()
    arr = np.arange(20, dtype=np.float32)
    v.set_data(arr)
    v.set_pixel_size(0.5, "nm")
    assert v._canvas._pixel_size == 0.5
    # x_disp should be scaled: arange(20) * 0.5
    np.testing.assert_allclose(v._canvas._x_disp, np.arange(20) * 0.5)


# ---------------------------------------------------------------------------
# Log scale
# ---------------------------------------------------------------------------

def test_set_log_y():
    v = _view()
    v.set_data(np.arange(1, 11, dtype=np.float32))
    v._canvas.set_log_y(True)
    assert v._canvas._ax.get_yscale() == "log"
    v._canvas.set_log_y(False)
    assert v._canvas._ax.get_yscale() == "linear"


def test_set_log_x():
    v = _view()
    v.set_data(np.arange(1, 11, dtype=np.float32))
    v._canvas.set_log_x(True)
    assert v._canvas._ax.get_xscale() == "log"
    v._canvas.set_log_x(False)
    assert v._canvas._ax.get_xscale() == "linear"


# ---------------------------------------------------------------------------
# reset_zoom
# ---------------------------------------------------------------------------

def test_reset_zoom_no_data():
    v = _view()
    v._canvas.reset_zoom()           # must not crash


def test_reset_zoom_with_data():
    v = _view()
    v.set_data(np.arange(50, dtype=np.float32))
    v._canvas.reset_zoom()           # must not crash


# ---------------------------------------------------------------------------
# Log checkbox enable/disable based on data sign
# ---------------------------------------------------------------------------

def test_log_checkboxes_disabled_when_no_positive_y():
    v = _view()
    v.set_data(np.full(20, -1.0, dtype=np.float32))
    assert not v._log_y_check.isEnabled()


def test_log_x_disabled_when_no_positive_x():
    v = _view()
    # (2, N) with all-negative x values
    x = np.full(20, -1.0)
    y = np.ones(20)
    v.set_data(np.stack([x, y]))
    assert not v._log_x_check.isEnabled()


def test_log_checkboxes_enabled_when_data_has_positive():
    v = _view()
    v.set_data(np.arange(1, 21, dtype=np.float32))
    assert v._log_x_check.isEnabled()
    assert v._log_y_check.isEnabled()
