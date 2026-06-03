from __future__ import annotations

import numpy as np

from npyquick.views.image import ImageView


def _silent_status(_msg: str) -> None:
    pass


def test_set_pixel_size_scales_endpoints():
    iv = ImageView(_silent_status)
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
    iv = ImageView(_silent_status)
    iv.set_data(np.arange(10).reshape(10, 1).astype(np.float32))

    iv.set_pixel_size(2.0, "μm")
    ep_after_2 = iv._canvas._endpoints.copy()

    iv.set_pixel_size(3.0, "μm")
    ep_after_3 = iv._canvas._endpoints.copy()

    np.testing.assert_allclose(ep_after_3, ep_after_2 * 1.5)


def test_pixel_size_propagates_to_profile():
    iv = ImageView(_silent_status)
    iv.set_data(np.zeros((10, 10), dtype=np.float32))
    iv.set_pixel_size(0.5, "mm")
    assert iv._canvas._profile._pixel_size == 0.5
    assert iv._canvas._profile._unit == "mm"


def test_set_pixel_size_before_data_is_safe():
    iv = ImageView(_silent_status)
    # no data loaded yet
    iv.set_pixel_size(2.0, "μm")
    assert iv._canvas._pixel_size == 2.0
    # subsequent load uses the new pixel_size
    iv.set_data(np.zeros((10, 20), dtype=np.float32))
    h, w = 10, 20
    ext = iv._canvas._im.get_extent()
    assert ext[0] == -0.5 * 2.0
    assert ext[1] == (w - 0.5) * 2.0


def test_image_view_handles_rgb():
    iv = ImageView(_silent_status)
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
