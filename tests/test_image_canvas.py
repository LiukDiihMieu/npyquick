from __future__ import annotations

import numpy as np

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


def test_can_handle_classmethod():
    assert ImageView.can_handle(np.zeros((10, 10), dtype=np.float32)) is True
    assert ImageView.can_handle(np.zeros((10, 10, 3), dtype=np.uint8)) is True
    assert ImageView.can_handle(np.zeros((10, 10, 4), dtype=np.uint8)) is False
    assert ImageView.can_handle(np.arange(10)) is False


# ---------------------------------------------------------------------------
# RGB normalization (_prepare_rgb)
# ---------------------------------------------------------------------------

def _make_canvas() -> ImageCanvas:
    return ImageCanvas(ProfileCanvas())


def test_prepare_rgb_uint8_divides_by_255():
    data = np.full((4, 4, 3), 128, dtype=np.uint8)
    display, norm_str = ImageCanvas._prepare_rgb(data)
    np.testing.assert_allclose(display, 128 / 255, atol=1e-6)
    assert "255" in norm_str


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
