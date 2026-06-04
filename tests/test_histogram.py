"""Tests for HistogramView and HistogramCanvas."""
from __future__ import annotations

import numpy as np
import pytest

from npyquick.views.histogram import HistogramCanvas, HistogramView


# ---------------------------------------------------------------------------
# can_handle
# ---------------------------------------------------------------------------

def test_can_handle_2d_float():
    assert HistogramView.can_handle(np.zeros((8, 8), dtype=np.float32))


def test_can_handle_1d_int():
    assert HistogramView.can_handle(np.arange(10, dtype=np.int32))


def test_can_handle_3d_rgb():
    assert HistogramView.can_handle(np.zeros((8, 8, 3), dtype=np.uint8))


def test_cannot_handle_string_array():
    assert not HistogramView.can_handle(np.array(["a", "b"]))


def test_cannot_handle_empty_array():
    assert not HistogramView.can_handle(np.empty((0, 5)))


# ---------------------------------------------------------------------------
# set_data — labels and anomaly visibility
# ---------------------------------------------------------------------------

def test_set_data_clean_hides_anomaly_label():
    v = HistogramView()
    v.set_data(np.array([1.0, 2.0, 3.0], dtype=np.float32))
    assert v._anomaly_label.isHidden()


def test_set_data_with_nan_shows_anomaly_label():
    v = HistogramView()
    arr = np.array([1.0, np.nan, 2.0], dtype=np.float32)
    v.set_data(arr)
    assert not v._anomaly_label.isHidden()
    assert "NaN: 1" in v._anomaly_label.text()


def test_set_data_stats_label_contains_min_max():
    v = HistogramView()
    v.set_data(np.array([1.0, 2.0, 3.0], dtype=np.float64))
    text = v._stats_label.text()
    assert "min" in text and "max" in text
    assert "mean" in text and "std" in text
    assert "p50" in text


def test_set_data_all_nan_shows_no_finite_message():
    v = HistogramView()
    v.set_data(np.array([np.nan, np.nan], dtype=np.float32))
    assert "no finite values" in v._stats_label.text()
    assert not v._anomaly_label.isHidden()


# ---------------------------------------------------------------------------
# HistogramCanvas — plot and bins
# ---------------------------------------------------------------------------

def test_canvas_plot_does_not_crash():
    c = HistogramCanvas()
    c.plot(np.random.rand(100).astype(np.float32))


def test_canvas_plot_all_nan_does_not_crash():
    c = HistogramCanvas()
    c.plot(np.full(10, np.nan, dtype=np.float32))
    assert c._edges is None


def test_canvas_bins_change_rerenders():
    c = HistogramCanvas()
    c.plot(np.arange(100, dtype=np.float32))
    assert c._edges is not None
    c.set_bins(64)
    assert len(c._counts) == 64


def test_canvas_log_scale_toggle_does_not_crash():
    c = HistogramCanvas()
    c.plot(np.arange(1, 101, dtype=np.float32))
    c.set_log_scale(True)
    c.set_log_scale(False)


# ---------------------------------------------------------------------------
# Clim marker — driven by update_clim_marker (called by app.py after ImageView)
# ---------------------------------------------------------------------------

def test_update_clim_marker_sets_vlines():
    v = HistogramView()
    v.set_data(np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32))
    v.update_clim_marker(1.0, 4.0)
    assert v._canvas._clim == pytest.approx((1.0, 4.0))
    assert v._canvas._vline_lo is not None
    assert v._canvas._vline_hi is not None


def test_update_clim_marker_none_clears_vlines():
    v = HistogramView()
    v.set_data(np.arange(10, dtype=np.float32))
    v.update_clim_marker(None, None)
    assert v._canvas._clim is None
    assert v._canvas._vline_lo is None


def test_set_data_resets_clim():
    v = HistogramView()
    v.set_data(np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32))
    assert v._canvas._clim is None  # reset; app.py syncs afterward


# ---------------------------------------------------------------------------
# Hover status
# ---------------------------------------------------------------------------

def test_hover_calls_status_callback():
    messages = []
    c = HistogramCanvas()
    c.set_on_status(messages.append)
    c.plot(np.arange(100, dtype=np.float32))

    class FakeEvent:
        inaxes = c._ax
        xdata = 50.0

    c._on_motion(FakeEvent())
    assert messages and "bin" in messages[-1] and "count" in messages[-1]


def test_axes_leave_restores_idle_status():
    messages = []
    c = HistogramCanvas()
    c.set_on_status(messages.append)
    c.set_idle_status("idle msg")
    c._on_axes_leave(None)
    assert messages[-1] == "idle msg"
