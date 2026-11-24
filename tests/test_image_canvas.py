from __future__ import annotations

import numpy as np
import pytest
from matplotlib.backend_bases import MouseEvent
from PySide6.QtWidgets import QToolBar

from npyquick.core.profile import compute_profile
from npyquick.views.image import ImageCanvas, ImageView, ProfileCanvas


def test_set_pixel_size_scales_endpoints():
    iv = ImageView()
    iv.set_data(np.zeros((10, 20), dtype=np.float32))
    ep0 = iv._canvas._endpoints.copy()

    iv.set_pixel_size(2.0, "μm")
    ep_after_2 = iv._canvas._endpoints.copy()
    np.testing.assert_allclose(ep_after_2, ep0 * 2.0)

    iv.set_pixel_size(3.0, "μm")
    ep_after_3 = iv._canvas._endpoints.copy()
    np.testing.assert_allclose(ep_after_3, ep_after_2 * 1.5)


def test_set_pixel_size_w1_regression():
    """Regression: w==1 used to fall back to old_ps=1.0, mis-scaling endpoints."""
    iv = ImageView()
    iv.set_data(np.arange(10).reshape(10, 1).astype(np.float32))

    iv.set_pixel_size(2.0, "μm")
    ep_after_2 = iv._canvas._endpoints.copy()

    iv.set_pixel_size(3.0, "μm")
    ep_after_3 = iv._canvas._endpoints.copy()

    np.testing.assert_allclose(ep_after_3, ep_after_2 * 1.5)


def test_pixel_size_propagates_to_profile():
    iv = ImageView()
    iv.set_data(np.zeros((10, 10), dtype=np.float32))
    iv.set_pixel_size(0.5, "mm")
    assert iv._canvas._profile._transform.pixel_size == 0.5
    assert iv._canvas._profile._transform.unit == "mm"


def test_set_pixel_size_before_data_is_safe():
    iv = ImageView()
    # no data loaded yet
    iv.set_pixel_size(2.0, "μm")
    assert iv._canvas._transform.pixel_size == 2.0
    # subsequent load uses the new pixel_size
    iv.set_data(np.zeros((10, 20), dtype=np.float32))
    h, w = 10, 20
    ext = iv._canvas._im.get_extent()
    assert ext[0] == -0.5 * 2.0
    assert ext[1] == (w - 0.5) * 2.0


def test_image_view_handles_rgb():
    iv = ImageView()
    rgb = np.zeros((10, 10, 3), dtype=np.uint8)
    iv.set_data(rgb)
    # vmin/vmax controls disabled for RGB
    assert not iv._vmin_edit.isEnabled()
    assert not iv._apply_btn.isEnabled()


def test_toolbar_toggle_restores_line_zoom_width_and_preference(image_settings, qapp):
    # A splitter collapsed in a previous release should reopen at a usable width.
    image_settings.setValue("image_profile_splitter", [800, 0])
    view = ImageView()
    view.resize(900, 480)
    view.show()
    view.set_data(np.arange(1024).reshape(32, 32))
    qapp.processEvents()
    canvas = view._canvas
    button = view.findChild(QToolBar).widgetForAction(view._profile_action)
    assert view._profile.isHidden() and not button.isChecked()
    assert canvas.profile_data() is None
    assert all(not a.get_visible() for a in (canvas._cs_line, canvas._ep0, canvas._ep1))
    x, y = canvas._ax.transData.transform(canvas.get_endpoints()[0])
    canvas.callbacks.process("button_press_event", MouseEvent("button_press_event", canvas, x, y, button=1))
    assert canvas._dragging is None and canvas._pan_start is not None
    assert "EP1" not in canvas.status_str()
    canvas._finish_drag()

    button.click()
    qapp.processEvents()
    assert view._profile.isVisible() and view._profile.width() > 100
    assert all(a.get_visible() for a in (canvas._cs_line, canvas._ep0, canvas._ep1))
    endpoints = [[5, 7], [24, 17]]
    canvas.set_endpoints(endpoints)
    canvas.set_view((2, 27), (23, 3))
    view._profile_splitter.moveSplitter(455, 1)
    sizes = view._profile_splitter.sizes()
    assert ImageView()._profile_action.isChecked()

    for _ in range(2):
        button.click()
        qapp.processEvents()
    np.testing.assert_array_equal(canvas.get_endpoints(), endpoints)
    assert canvas.get_view() == ((2, 27), (23, 3))
    assert view._profile_splitter.sizes() == sizes
    button.click()
    assert not ImageView()._profile_action.isChecked()
    view.close()


def test_disabled_profile_skips_sampling_and_reopens_on_current_data(image_settings, monkeypatch):
    view = ImageView()
    y, x = np.mgrid[:16, :20]
    with monkeypatch.context() as m:
        def unexpected_sample(*args):
            pytest.fail("Profile sampled while the tool was off")

        m.setattr("npyquick.views.image.compute_profile", unexpected_sample)
        view.set_data(x)
        view.set_data(x + 1j * y)
        view.set_pixel_size(2, "mm")
        view._on_canvas_clicked(view._canvas_b)
    view._profile_action.trigger()
    a, b = view._canvas, view._canvas_b
    np.testing.assert_array_equal(a.get_endpoints(), b.get_endpoints())
    distances, values = compute_profile(y, *(b.get_endpoints() / 2))
    line = view._profile._lines[0]
    np.testing.assert_allclose(line.get_xdata(), distances * 2)
    np.testing.assert_allclose(line.get_ydata(), values)
    assert view._profile._ylabel == "Imag"
    view._profile_action.trigger()
    view.set_data(np.ones((8, 12, 3), dtype=np.uint8))
    view._profile_action.trigger()
    assert len(view._profile._lines) == 3


def test_hover_over_endpoint_hints_drag_else_shows_readout(profile_view):
    """Resting on a cross-section endpoint hints 'drag'; elsewhere the live
    pixel readout is left untouched so value-scanning is undisturbed."""
    from types import SimpleNamespace

    iv = profile_view
    iv.set_data(np.arange(100, dtype=float).reshape(10, 10))
    canvas = iv._canvas
    seen = []
    canvas.set_on_status(lambda msg, *a: seen.append(msg))

    ep = canvas._endpoints[0]
    canvas._on_motion(SimpleNamespace(
        inaxes=canvas._ax, xdata=float(ep[0]), ydata=float(ep[1]), x=0, y=0,
    ))
    assert "Drag to move" in seen[-1]

    canvas._on_motion(SimpleNamespace(
        inaxes=canvas._ax, xdata=float(ep[0]) + 50, ydata=float(ep[1]) + 50,
        x=0, y=0,
    ))
    assert "Drag to move" not in seen[-1]


def test_invalid_clim_input_reports_status_and_does_not_raise():
    iv = ImageView()
    iv.set_data(np.arange(100, dtype=np.float32).reshape(10, 10))
    seen = []
    iv.set_on_status(lambda msg, *a: seen.append(msg))
    iv._vmin_edit.setText("abc")  # non-numeric
    iv._apply_clim()  # must not raise
    assert any("must be numbers" in m for m in seen)


def test_can_handle_classmethod():
    assert ImageView.can_handle(np.zeros((10, 10), dtype=np.float32)) is True
    assert ImageView.can_handle(np.zeros((10, 10, 3), dtype=np.uint8)) is True
    assert ImageView.can_handle(np.zeros((10, 10, 4), dtype=np.uint8)) is False
    assert ImageView.can_handle(np.arange(10)) is False


@pytest.mark.parametrize("shape", [
    (0, 5),       # empty rows, 2D
    (5, 0),       # empty cols, 2D
    (0, 0),       # empty 2D
    (0, 5, 3),    # empty RGB
])
def test_can_handle_rejects_empty_arrays(shape):
    """Guards the `array.size > 0` check in can_handle for both 2D and RGB —
    a zero-element array would otherwise crash imshow at render time."""
    assert ImageView.can_handle(np.empty(shape, dtype=float)) is False


# ---------------------------------------------------------------------------
# RGB normalization (_prepare_rgb)
# ---------------------------------------------------------------------------

def _make_canvas() -> ImageCanvas:
    return ImageCanvas(ProfileCanvas())


def test_prepare_rgb_uint8_passthrough():
    data = np.full((4, 4, 3), 128, dtype=np.uint8)
    display, norm_str = ImageCanvas._prepare_rgb(data)
    assert display.dtype == np.uint8
    np.testing.assert_array_equal(display, 128)
    assert "as-is" in norm_str


def test_prepare_rgb_uint16_divides_by_65535():
    data = np.full((4, 4, 3), 32768, dtype=np.uint16)
    display, norm_str = ImageCanvas._prepare_rgb(data)
    np.testing.assert_allclose(display, 32768 / 65535, atol=1e-4)
    assert "65535" in norm_str
    assert "uint16" in norm_str


def test_prepare_rgb_float_in_01_is_asis():
    data = np.full((4, 4, 3), 0.5, dtype=np.float32)
    display, norm_str = ImageCanvas._prepare_rgb(data)
    np.testing.assert_allclose(display, 0.5, atol=1e-6)
    assert "as-is" in norm_str


def test_prepare_rgb_float_arbitrary_range_minmax():
    data = np.zeros((4, 4, 3), dtype=np.float32)
    data[0, 0, 0] = -1.0
    data[3, 3, 2] = 3.0
    display, norm_str = ImageCanvas._prepare_rgb(data)
    assert display.min() >= 0.0
    assert display.max() <= 1.0
    assert "min-max" in norm_str
    assert "-1" in norm_str


def test_norm_label_visible_for_rgb():
    iv = ImageView()
    iv.set_data(np.zeros((8, 8, 3), dtype=np.uint8))
    assert not iv._norm_label.isHidden()
    assert iv._norm_label.text().startswith("norm:")


def test_norm_label_hidden_for_grayscale():
    iv = ImageView()
    iv.set_data(np.zeros((8, 8), dtype=np.float32))
    assert iv._norm_label.isHidden()
