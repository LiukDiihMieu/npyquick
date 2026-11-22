from threading import Event

import numpy as np
import pytest
from matplotlib.backend_bases import MouseEvent
from PySide6.QtCore import QThreadPool

from npyquick.core import limits, roi
from npyquick.core.roi import PixelRect, region_stats
from npyquick.views import roi as roi_widgets
from npyquick.views.image import ImageView


def test_exact_stats_across_blocks_and_invalid_values(monkeypatch):
    monkeypatch.setattr(roi, "BLOCK_VALUES", 3)
    base = np.arange(180, dtype=float).reshape(12, 15) + 1e12
    base[3, 8:10] = [np.nan, np.inf]
    crop = base[1:9:2, 5:11].T[::-1]
    finite = crop[np.isfinite(crop)]
    stats = region_stats(crop)
    assert stats.count == len(finite)
    assert stats.mean == pytest.approx(finite.mean(), abs=0.001, rel=0)
    assert stats.std == pytest.approx(finite.std())
    assert (stats.minimum, stats.maximum) == (finite.min(), finite.max())
    assert region_stats(np.array([np.inf, np.nan])) == (0, None, None, None, None)
    with pytest.raises(InterruptedError):
        region_stats(crop, cancelled=lambda: True)


def test_phase_wrap_and_undefined_phase():
    values = np.array([np.exp(1j * (np.pi - 0.1)), np.exp(-1j * (np.pi - 0.1)), 0, np.nan])
    stats = region_stats(values, "Angle")
    assert stats.count == 2
    assert abs(stats.mean) == pytest.approx(np.pi)
    assert stats.std == pytest.approx(np.sqrt(-2 * np.log(np.cos(0.1))))
    assert stats.minimum == pytest.approx(-np.pi + 0.1)
    assert stats.maximum == pytest.approx(np.pi - 0.1)
    assert region_stats(np.array([1+0j, -1+0j]), "Angle") == (2, None, np.inf, 0, np.pi)
    text = roi_widgets._measure(values.reshape(2, 2), "Angle", Event())
    assert "Min -3.0416   Max 3.0416  (rad)" in text


def test_large_integer_measurements_with_double_precision(monkeypatch):
    monkeypatch.setattr(roi, "BLOCK_VALUES", 1)
    monkeypatch.setattr(roi.np, "longdouble", np.float64)
    data = np.array([[2**63 + 1, 2**63 + 2]], dtype=np.uint64)
    text = roi_widgets._measure(data, None, Event())
    assert "Std 0.5   Min 9223372036854775809   Max 9223372036854775810" in text
    assert region_stats(np.array([-2**63, -2**63 + 1])).std == 0.5


def test_circular_std_resolves_tightly_clustered_phases(monkeypatch):
    monkeypatch.setattr(roi, "BLOCK_VALUES", 3)
    phase = 0.7
    spread = 1e-9
    phases = np.tile([phase - spread, phase + spread], 5)
    stats = region_stats(np.exp(1j * phases), "Angle")
    assert stats.mean == pytest.approx(phase)
    assert stats.std == pytest.approx(spread, rel=1e-6, abs=0)
    assert region_stats(np.full(10, 3 + 4j), "Angle").std == 0


def mouse(canvas, event, xy):
    x, y = canvas._ax.transData.transform(xy)
    canvas.callbacks.process(event, MouseEvent(event, canvas, x, y, button=1))


@pytest.fixture
def view(image_settings):
    widget = ImageView()
    widget.resize(960, 540)
    widget.show()
    yield widget
    widget.close()


def test_draw_move_resize_and_replace_on_original_pixels(view, qapp, monkeypatch):
    monkeypatch.setattr(limits, "IMAGE_MAX_PIXELS", 100)
    data = np.zeros((30, 40))
    data[6, 6] = 400  # Missed by the strided preview.
    data[4, 5] = np.nan
    view._roi_action.trigger()
    view.set_data(data)
    qapp.processEvents()
    c = view._canvas
    assert c._stride > 1
    mouse(c, "button_press_event", (8, 9))
    mouse(c, "motion_notify_event", (3, 4))
    assert view._roi_readout.text() == "ROI  6 × 6 px"
    mouse(c, "button_release_event", (3, 4))
    assert c.roi.bounds == PixelRect(3, 4, 9, 10)
    assert "Mean 11.429" in view._roi_readout.text()
    assert "Min 0   Max 400" in view._roi_readout.text()
    assert "Valid 35/36" in view._roi_readout.text()

    mouse(c, "button_press_event", (5, 6))
    mouse(c, "button_release_event", (55, 43))  # beyond the bottom-right boundary
    assert c.roi.bounds == PixelRect(34, 24, 40, 30)
    mouse(c, "button_press_event", (33.51, 23.51))
    mouse(c, "button_release_event", (30.51, 21.51))
    assert c.roi.bounds == PixelRect(31, 22, 40, 30)
    mouse(c, "button_press_event", (2, 2))
    mouse(c, "button_release_event", (5, 4))
    assert c.roi.bounds == PixelRect(2, 2, 6, 5)
    view.set_pixel_size(0.5, "μm")
    assert "4 × 3 px  (2 × 1.5 μm)" in view._roi_readout.text()
    np.testing.assert_allclose(c.roi.artist.get_xydata()[0], [0.75, 0.75])
    view.set_data(data[:5, :5])
    assert c.roi.bounds is None and not c.roi.artist.get_visible()
    assert "Mean" not in view._roi_readout.text()


def test_tools_restore_and_complex_panels_share_region(image_settings, qapp):
    image_settings.setValue("image_profile_enabled", True)
    view = ImageView()
    view.resize(960, 540)
    view.show()
    assert view._profile_action.isChecked()
    view.set_data(np.full((30, 40), 3+4j))
    a, b = view._canvas, view._canvas_b
    endpoints = a.get_endpoints() + 1
    a.set_endpoints(endpoints)
    view._on_endpoints_dragged(a)
    view._roi_action.trigger()
    qapp.processEvents()
    mouse(b, "button_press_event", (1, 2))
    mouse(b, "button_release_event", (12, 14))
    rect = PixelRect(1, 2, 13, 15)
    assert a.roi.bounds == b.roi.bounds == rect
    assert "Imag  Mean 4" in view._roi_readout.text()
    # A click outside on the other panel changes the readout without replacing the ROI.
    mouse(a, "button_press_event", (20, 20))
    mouse(a, "button_release_event", (20, 20))
    assert a.roi.bounds == rect
    assert "Real  Mean 3" in view._roi_readout.text()
    view.set_pair("Abs / Angle")
    assert "Abs  Mean 5" in view._roi_readout.text()
    assert ImageView()._roi_action.isChecked()
    view._profile_action.trigger()
    assert view._profile.isVisible() and not view._roi_readout.isVisible()
    assert not a.roi.artist.get_visible() and not b.roi.artist.get_visible()
    np.testing.assert_array_equal(b.get_endpoints(), endpoints)
    view._roi_action.trigger()
    assert a.roi.artist.get_visible() and a.roi.bounds == rect
    view._roi_action.trigger()
    assert not a.roi.artist.get_visible() and not view._profile_action.isChecked()
    assert image_settings.value("image_tool") == "none"
    view.close()


def test_one_pixel_memmap_selection_and_interrupted_drag(view, tmp_path, qapp):
    path = tmp_path / "sensor.npy"
    np.save(path, np.arange(48).reshape(6, 8))
    view.set_data(np.load(path, mmap_mode="r"))
    view._roi_action.trigger()
    qapp.processEvents()
    c = view._canvas
    mouse(c, "button_press_event", (2.1, 3.1))
    mouse(c, "button_release_event", (2.4, 3.4))
    assert c.roi.bounds == PixelRect(2, 3, 3, 4)
    assert QThreadPool.globalInstance().waitForDone(5000)
    qapp.processEvents()
    assert "Mean 26   Std 0   Min 26   Max 26" in view._roi_readout.text()
    mouse(c, "button_press_event", (4, 1))
    mouse(c, "motion_notify_event", (6, 4))
    view._profile_action.trigger()  # Interrupt before mouse release.
    assert c.roi.drag is None
    assert not c.roi.artist.get_animated() and not c.roi.artist.get_visible()
    assert not c._drag_layouts and c._drag_background is None
    view._roi_action.trigger()
    assert c.roi.bounds == PixelRect(4, 1, 7, 5)


def test_background_rgb_measurement_ignores_superseded_result(view, qapp, monkeypatch):
    monkeypatch.setattr(roi_widgets, "BLOCK_VALUES", 4)
    started, release = Event(), Event()
    measure = roi_widgets._measure

    def delayed(region, component, cancelled):
        if region[0, 0, 0] == 100:
            started.set()
            assert release.wait(5)
            return "stale result"
        return measure(region, component, cancelled)

    monkeypatch.setattr(roi_widgets, "_measure", delayed)
    rgb = np.zeros((20, 32, 3), dtype=np.uint16)
    rgb[:, :8] = [100, 200, 300]
    rgb[:, 8:] = [900, 400, 200]
    rgb[1, 12] = [898, 390, 192]
    rgb[2, 12] = [902, 410, 208]
    view.set_data(rgb)
    view._roi_action.trigger()
    qapp.processEvents()
    view._set_roi(PixelRect(0, 0, 6, 6), True)
    try:
        assert started.wait(3)
        assert "Measuring" in view._roi_readout.text()
        view._set_roi(PixelRect(12, 0, 20, 8), True)
    finally:
        release.set()
    assert QThreadPool.globalInstance().waitForDone(5000)
    qapp.processEvents()
    text = view._roi_readout.text()
    assert "R  Mean 900" in text and "G  Mean 400" in text and "B  Mean 200" in text
    view.resize(450, 540)
    qapp.processEvents()
    lines = view._roi_readout.text().splitlines()
    assert lines[1].endswith("Min 898   Max 902")
    assert lines[2].endswith("Min 390   Max 410")
    assert lines[3].endswith("Min 192   Max 208")
    view.resize(1600, 540)
    qapp.processEvents()
    assert len(view._roi_readout.text().splitlines()) == 1
