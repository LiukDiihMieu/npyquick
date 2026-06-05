"""Compare (DualImageView) regression + feature tests.

Constructs DualImageView directly (conftest provides offscreen QApplication).
Img 2 is loaded from a temp .npy via the same `_load_img2` path the GUI uses.
"""
from __future__ import annotations

import numpy as np

from npyquick.core import limits
from npyquick.views.dual_image import DualImageView


def _img(seed: int = 0, shape: tuple[int, int] = (10, 20)) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.standard_normal(shape).astype(np.float32)


def _save(tmp_path, name: str, arr: np.ndarray) -> str:
    p = tmp_path / name
    np.save(p, arr)
    return str(p)


def test_set_data_loads_img1():
    v = DualImageView()
    v.set_data(_img())
    assert v._img1 is not None
    assert v._img2 is None


def test_can_handle_always_true():
    assert DualImageView.can_handle(np.zeros((10, 10))) is True
    assert DualImageView.can_handle(np.arange(5)) is True


def test_diff_canvas_matches_img2_zoom_on_show(tmp_path):
    """Regression: Show Diff must adopt Img 2's zoom, not the full extent."""
    v = DualImageView()
    v.set_data(_img(0))
    v._load_img2(_save(tmp_path, "i2.npy", _img(1)))
    v._canvas2.set_view((2.0, 8.0), (6.0, 1.0))
    v._toggle_diff(True)
    assert v._diff_canvas.get_view() == v._canvas2.get_view()


def test_img1_endpoint_change_syncs_to_diff(tmp_path):
    v = DualImageView()
    v.set_data(_img(0))
    v._load_img2(_save(tmp_path, "i2.npy", _img(1)))
    v._toggle_diff(True)
    new_eps = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=float)
    v._on_img1_endpoints_changed(new_eps)
    np.testing.assert_allclose(v._diff_canvas.get_endpoints(), new_eps)


def test_align_copies_endpoints_and_view(tmp_path):
    v = DualImageView()
    v.set_data(_img(0))
    v._load_img2(_save(tmp_path, "i2.npy", _img(1)))
    v._canvas1.set_endpoints(np.array([[0.5, 1.5], [2.5, 3.5]], dtype=float))
    v._canvas1.set_view((1.0, 9.0), (8.0, 2.0))
    v._align_endpoints()
    np.testing.assert_allclose(
        v._canvas2.get_endpoints(), v._canvas1.get_endpoints()
    )
    assert v._canvas2.get_view() == v._canvas1.get_view()
    assert v._diff_canvas.get_view() == v._canvas1.get_view()


def test_load_img2_shape_mismatch_rejected(tmp_path):
    v = DualImageView()
    v.set_data(_img(0, shape=(10, 20)))
    v._load_img2(_save(tmp_path, "bad.npy", _img(1, shape=(5, 5))))
    assert v._img2 is None


def test_load_img2_non_2d_rejected(tmp_path):
    v = DualImageView()
    v.set_data(_img(0))
    v._load_img2(_save(tmp_path, "vec.npy", np.arange(10, dtype=np.float32)))
    assert v._img2 is None


def test_load_img2_npz_rejected(tmp_path):
    v = DualImageView()
    v.set_data(_img(0))
    p = tmp_path / "arch.npz"
    np.savez(p, a=_img(1))
    v._load_img2(str(p))
    assert v._img2 is None


def test_load_img2_large_is_memmap(tmp_path, monkeypatch):
    monkeypatch.setattr(limits, "LARGE_BYTES", 0)  # everything counts as large
    v = DualImageView()
    v.set_data(_img(0, shape=(8, 8)))
    v._load_img2(_save(tmp_path, "big.npy", _img(1, shape=(8, 8))))
    assert isinstance(v._model2.array, np.memmap)


def test_set_data_downsamples_large_image(monkeypatch):
    monkeypatch.setattr(limits, "IMAGE_MAX_PIXELS", 16)
    v = DualImageView()
    v.set_data(_img(0, shape=(8, 8)))
    c = v._canvas1
    assert c._stride > 1
    assert c._disp.size < c._data.size
    assert c._data.shape == (8, 8)  # full resolution retained for hover


def test_get_profile_uses_display_array(tmp_path):
    v = DualImageView()
    v.set_data(_img(0))
    c = v._canvas1
    assert np.issubdtype(c._disp.dtype, np.floating)
    result = c.get_profile()
    assert result is not None
    dists, values = result
    assert len(dists) == len(values) > 0
