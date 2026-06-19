"""Tests for HistogramView and HistogramCanvas."""
from __future__ import annotations

import warnings

import numpy as np
import pytest

from npyquick.views.histogram import HistogramCanvas, HistogramView
from npyquick.views.image import ImageView


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


def test_can_handle_complex_1d():
    assert HistogramView.can_handle(np.array([1+2j, 3+4j], dtype=np.complex128))


def test_can_handle_complex_2d():
    assert HistogramView.can_handle(np.zeros((4, 4), dtype=np.complex64))


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
    c.plot(np.random.default_rng(0).random(100).astype(np.float32))


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


def test_xlim_robust_constant_array_no_singular_warning():
    c = HistogramCanvas()
    c.plot(np.full(100, 3.0, dtype=np.float32))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        c.xlim_robust()
    lo, hi = c._ax.get_xlim()
    assert hi > lo


def test_xlim_robust_constant_zero_array_no_singular_warning():
    c = HistogramCanvas()
    c.plot(np.zeros(100, dtype=np.float32))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        c.xlim_robust()
    lo, hi = c._ax.get_xlim()
    assert hi > lo


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


# ---------------------------------------------------------------------------
# Regression: stale clim marker from previous Image array
# ---------------------------------------------------------------------------

def _simulate_refresh(image_view, histogram_view, array):
    """Mirror _refresh_views() clim logic."""
    histogram_view.set_data(array)
    if ImageView.can_handle(array):
        histogram_view.update_clim_marker(*image_view.get_clim())
    else:
        histogram_view.update_clim_marker(None, None)


def test_clim_marker_cleared_when_switching_to_non_image_array():
    iv = ImageView()
    hv = HistogramView()

    image_2d = np.arange(9, dtype=np.float32).reshape(3, 3)
    _simulate_refresh(iv, hv, image_2d)
    iv.set_data(image_2d)
    hv.update_clim_marker(*iv.get_clim())
    assert hv._canvas._clim is not None, "clim should be set after image load"

    line_1d = np.arange(10, dtype=np.float32)
    _simulate_refresh(iv, hv, line_1d)
    assert hv._canvas._clim is None, "clim must be cleared when array is not image-compatible"
    assert hv._canvas._vline_lo is None
    assert hv._canvas._vline_hi is None


def test_clim_marker_preserved_when_switching_between_images():
    iv = ImageView()
    hv = HistogramView()

    img_a = np.arange(9, dtype=np.float32).reshape(3, 3)
    iv.set_data(img_a)
    _simulate_refresh(iv, hv, img_a)
    assert hv._canvas._clim is not None

    img_b = np.arange(16, dtype=np.float32).reshape(4, 4)
    iv.set_data(img_b)
    _simulate_refresh(iv, hv, img_b)
    assert hv._canvas._clim is not None


# ---------------------------------------------------------------------------
# no re-sample on bins / log-scale changes
# ---------------------------------------------------------------------------

def test_histogram_set_bins_reuses_cached_sample(monkeypatch):
    calls = 0

    def fake_finite_sample(array):
        nonlocal calls
        calls += 1
        return np.asarray(array), array.size, array.size

    monkeypatch.setattr("npyquick.views.histogram.finite_sample", fake_finite_sample)

    canvas = HistogramCanvas()
    arr = np.arange(100)
    canvas.plot(arr)
    assert calls == 1

    canvas.set_bins(64)
    assert calls == 1


def test_histogram_log_toggle_does_not_rerender_or_resample(monkeypatch):
    canvas = HistogramCanvas()
    arr = np.arange(100)
    canvas.plot(arr)

    called = False

    def fail_render():
        nonlocal called
        called = True

    monkeypatch.setattr(canvas, "_render", fail_render)
    canvas.set_log_scale(True)

    assert called is False
    assert canvas._ax.get_yscale() == "log"


# ---------------------------------------------------------------------------
# complex arrays: component projection
# ---------------------------------------------------------------------------

def _complex_grid():
    re = np.linspace(-2, 2, 64).reshape(8, 8)
    im = np.linspace(0, 3, 64).reshape(8, 8)
    return (re + 1j * im).astype(np.complex128)


def test_histogram_complex_default_magnitude_finite():
    view = HistogramView()
    view.set_data(_complex_grid())
    finite = view._canvas._finite
    assert finite is not None and finite.size > 0
    assert np.all(np.isfinite(finite))
    assert finite.min() >= 0.0  # magnitude is non-negative


def test_histogram_set_component_reprojects_without_resampling(monkeypatch):
    view = HistogramView()
    view.set_data(_complex_grid())

    sample_calls = 0
    real_sampler = __import__(
        "npyquick.core.limits", fromlist=["sampled_flat_view"]
    ).sampled_flat_view

    def spy_sampler(array, budget):
        nonlocal sample_calls
        sample_calls += 1
        return real_sampler(array, budget)

    monkeypatch.setattr("npyquick.views.histogram.limits.sampled_flat_view", spy_sampler)

    view.set_component("Angle")
    assert sample_calls == 0, "switching component must not re-sample"
    phase = view._canvas._finite
    assert np.all(phase > -np.pi - 1e-9) and np.all(phase <= np.pi + 1e-9)


def test_histogram_complex_projection_only_sees_sampled_data(monkeypatch):
    monkeypatch.setattr("npyquick.views.histogram.limits.HIST_MAX_SAMPLES", 16)
    seen = {}
    real_project = __import__(
        "npyquick.core.complexproj", fromlist=["project"]
    ).project

    def spy_project(arr, comp):
        seen["size"] = arr.size
        return real_project(arr, comp)

    monkeypatch.setattr("npyquick.views.histogram.complexproj.project", spy_project)
    view = HistogramView()
    view.set_data(_complex_grid())  # 64 elements, budget 16 → must sample down
    assert seen["size"] <= 16, "projection must run on the sampled subset only"
