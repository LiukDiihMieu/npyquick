"""Tests for ImageView complex dual-panel mode."""
from __future__ import annotations

import numpy as np

from npyquick.views.image import ImageView


def _complex(h=12, w=16):
    re = np.linspace(-1, 1, h * w).reshape(h, w)
    im = np.linspace(0, 2, h * w).reshape(h, w)
    return (re + 1j * im).astype(np.complex128)


def test_can_handle_complex_2d():
    assert ImageView.can_handle(_complex())
    assert ImageView.can_handle(np.zeros((4, 4), dtype=np.float32))
    assert not ImageView.can_handle(np.zeros(5, dtype=np.complex128))  # 1D
    assert not ImageView.can_handle(np.zeros((2, 2), dtype=object))


def test_complex_set_data_shows_two_real_panels():
    iv = ImageView()
    iv.set_data(_complex())
    assert iv._complex is True
    assert not iv._canvas_b.isHidden()
    assert not np.iscomplexobj(iv._canvas._disp)
    assert not np.iscomplexobj(iv._canvas_b._disp)
    # Default pair is Real / Imag.
    assert (iv._comp_a, iv._comp_b) == ("Real", "Imag")


def test_real_after_complex_hides_second_panel():
    iv = ImageView()
    iv.set_data(_complex())
    iv.set_data(np.zeros((8, 8), dtype=np.float32))
    assert iv._complex is False
    assert iv._canvas_b.isHidden()
    # Primary canvas's direct profile push is restored.
    assert iv._canvas._profile is iv._profile


def test_set_pair_flips_components_and_phase_clim():
    iv = ImageView()
    iv.set_data(_complex())
    iv.set_pair("Abs / Angle")
    assert (iv._comp_a, iv._comp_b) == ("Abs", "Angle")
    # Angle panel (B) clamps to (-pi, pi].
    vmin, vmax = iv._canvas_b._im.get_clim()
    assert vmin == -np.pi and vmax == np.pi
    # Abs panel (A) is non-negative.
    assert iv._canvas._disp.min() >= 0.0


def test_click_switches_active_profile_label_and_clim_prefix():
    iv = ImageView()
    iv.set_data(_complex())
    assert iv._active is iv._canvas
    assert iv._profile._ylabel == "Real"

    iv._on_canvas_clicked(iv._canvas_b)
    assert iv._active is iv._canvas_b
    assert iv._profile._ylabel == "Imag"
    assert iv._clim_prefix_label.text() == "Imag"


def test_continuous_linked_zoom_between_panels():
    iv = ImageView()
    iv.set_data(_complex())
    iv._canvas._apply_view((0, 4), (4, 0))   # as a zoom would
    assert iv._canvas_b.get_view() == ((0, 4), (4, 0))


def test_shared_cross_section_endpoints():
    iv = ImageView()
    iv.set_data(_complex())
    new_eps = np.array([[2.0, 3.0], [9.0, 5.0]])
    iv._canvas.set_endpoints(new_eps)
    iv._on_endpoints_dragged(iv._canvas)     # simulate the drag callback
    np.testing.assert_allclose(iv._canvas_b.get_endpoints(), new_eps)


def test_colormap_and_pixel_size_reach_both_panels():
    iv = ImageView()
    iv.set_data(_complex())
    iv.set_colormap("viridis")
    assert iv._canvas._colormap == "viridis"
    assert iv._canvas_b._colormap == "viridis"
    iv.set_pixel_size(0.5, "mm")
    assert iv._canvas._transform.pixel_size == 0.5
    assert iv._canvas_b._transform.pixel_size == 0.5


def test_complex_get_clim_reports_none():
    iv = ImageView()
    iv.set_data(_complex())
    assert iv.get_clim() == (None, None)


def test_complex_anomaly_count_shown():
    arr = _complex()
    arr[0, 0] = complex(np.nan, 0.0)
    arr[1, 1] = complex(np.inf, 1.0)
    arr[2, 2] = complex(1.0, -np.inf)
    iv = ImageView()
    iv.set_data(arr)
    assert not iv._anomaly_label.isHidden()
    txt = iv._anomaly_label.text()
    assert "NaN: 1" in txt and "Inf: 2" in txt


def test_export_targets_labels_for_complex():
    iv = ImageView()
    iv.set_data(_complex())
    names = [n for n, _ in iv.export_targets()]
    assert names == ["Real", "Imag", "Profile"]
    iv.set_pair("Abs / Angle")
    names = [n for n, _ in iv.export_targets()]
    assert names == ["Abs", "Angle", "Profile"]
