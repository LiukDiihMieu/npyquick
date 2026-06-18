"""Large-file handling: lazy npz, conditional mmap, downsampling, sampling.

All tests shrink the limits thresholds via monkeypatch so tiny arrays exercise
the large-file code paths (no multi-hundred-MB fixtures required).
"""
from __future__ import annotations

import numpy as np
import pytest

from npyquick.core import limits
from npyquick.core.stats import array_stats
from npyquick.model import NpyDataModel
from npyquick.views.histogram import HistogramView, finite_sample
from npyquick.views.image import ImageView


# ---------------------------------------------------------------------------
# model.py — conditional mmap for .npy
# ---------------------------------------------------------------------------

def test_large_npy_returns_memmap(tmp_path, monkeypatch):
    monkeypatch.setattr(limits, "LARGE_BYTES", 0)  # everything counts as large
    p = tmp_path / "big.npy"
    np.save(p, np.arange(64, dtype=np.float32).reshape(8, 8))
    m = NpyDataModel()
    m.load(str(p))
    assert isinstance(m.array, np.memmap)


def test_small_npy_is_not_memmap(tmp_path):
    p = tmp_path / "small.npy"
    np.save(p, np.arange(16, dtype=np.float32).reshape(4, 4))
    m = NpyDataModel()
    m.load(str(p))
    assert not isinstance(m.array, np.memmap)


def test_zero_d_npy_not_memmapped_even_when_large(tmp_path, monkeypatch):
    monkeypatch.setattr(limits, "LARGE_BYTES", 0)
    p = tmp_path / "scalar.npy"
    np.save(p, np.array(7.0))
    m = NpyDataModel()
    m.load(str(p))
    assert not isinstance(m.array, np.memmap)
    assert m.array.shape == ()


def test_structured_npy_memmapped_when_large(tmp_path, monkeypatch):
    # Structured dtypes are memory-mappable, so a large one is mapped like any
    # other array (only the table view handles it downstream).
    monkeypatch.setattr(limits, "LARGE_BYTES", 0)
    p = tmp_path / "rec.npy"
    rec = np.array([(1, 2.0), (3, 4.0)], dtype=[("a", "i4"), ("b", "f8")])
    np.save(p, rec)
    m = NpyDataModel()
    m.load(str(p))
    assert isinstance(m.array, np.memmap)
    assert m.array.dtype.names == ("a", "b")


def test_large_npy_mmap_failure_does_not_fall_back(tmp_path, monkeypatch):
    monkeypatch.setattr(limits, "LARGE_BYTES", 0)
    p = tmp_path / "big.npy"
    np.save(p, np.arange(64, dtype=np.float32).reshape(8, 8))

    import npyquick.model as model_mod
    real_load = np.load

    def fake_load(path, *args, **kwargs):
        if kwargs.get("mmap_mode"):
            raise OSError("simulated mmap failure")
        return real_load(path, *args, **kwargs)

    monkeypatch.setattr(model_mod.np, "load", fake_load)
    m = NpyDataModel()
    with pytest.raises(RuntimeError, match="could not be memory-mapped"):
        m.load(str(p))


# ---------------------------------------------------------------------------
# model.py — npz lazy loading + member ceiling
# ---------------------------------------------------------------------------

def test_npz_select_over_ceiling_raises(tmp_path, monkeypatch):
    small = np.zeros((2, 2), dtype=np.uint8)        # 4 bytes
    big = np.zeros((10, 10), dtype=np.float64)      # 800 bytes
    p = tmp_path / "mix.npz"
    np.savez(p, a_small=small, z_big=big)
    monkeypatch.setattr(limits, "NPZ_MEMBER_CEILING", 100)

    m = NpyDataModel()
    m.load(str(p))  # load only peeks metadata — no materialization here
    with pytest.raises(ValueError, match="exceeding"):
        m.select_array("z_big")


def test_npz_select_at_exact_ceiling_succeeds(tmp_path, monkeypatch):
    """The ceiling check is strict-greater-than: nbytes == ceiling must pass.
    Guards against an off-by-one regression of the inequality."""
    arr = np.zeros((10, 10), dtype=np.float64)      # 800 bytes
    p = tmp_path / "at_ceiling.npz"
    np.savez(p, x=arr)
    monkeypatch.setattr(limits, "NPZ_MEMBER_CEILING", arr.nbytes)

    m = NpyDataModel()
    m.load(str(p))
    m.select_array("x")  # must not raise

    assert m.array is not None
    assert m.array.shape == (10, 10)


def test_npz_large_first_member_does_not_block_load(tmp_path, monkeypatch):
    """Regression: opening an npz must succeed even if the first member exceeds
    NPZ_MEMBER_CEILING; the ceiling check only fires at select_array() time."""
    big = np.zeros((10, 10), dtype=np.float64)     # 800 bytes
    small = np.zeros((2, 2), dtype=np.uint8)        # 4 bytes
    p = tmp_path / "mixed.npz"
    np.savez(p, big_first=big, small=small)
    monkeypatch.setattr(limits, "NPZ_MEMBER_CEILING", big.nbytes - 1)

    m = NpyDataModel()
    m.load(str(p))                        # must not raise
    assert m.array is None
    assert set(m.available_array_meta().keys()) == {"big_first", "small"}

    with pytest.raises(ValueError, match="exceeding"):
        m.select_array("big_first")

    m.select_array("small")
    assert m.array is not None
    assert m.array.shape == (2, 2)


def test_npz_select_materializes_only_chosen(tmp_path):
    p = tmp_path / "two.npz"
    np.savez(p, x=np.full((2, 2), 1.0), y=np.full((3, 3), 2.0))
    m = NpyDataModel()
    m.load(str(p))
    m.select_array("y")
    np.testing.assert_array_equal(m.array, np.full((3, 3), 2.0))


# ---------------------------------------------------------------------------
# Fortran-order memmap: flatten must stay a view (no full-array copy) so the
# sampling budget actually protects against reading the whole file.
# ---------------------------------------------------------------------------

def _fortran_memmap(tmp_path, monkeypatch, shape=(8, 8)):
    monkeypatch.setattr(limits, "LARGE_BYTES", 0)
    p = tmp_path / "fortran.npy"
    arr = np.asfortranarray(np.arange(int(np.prod(shape)), dtype=np.float64).reshape(shape))
    np.save(p, arr)
    m = NpyDataModel()
    m.load(str(p))
    assert isinstance(m.array, np.memmap)
    assert m.array.flags["F_CONTIGUOUS"] and not m.array.flags["C_CONTIGUOUS"]
    return m.array


def test_stats_does_not_copy_fortran_memmap(tmp_path, monkeypatch):
    arr = _fortran_memmap(tmp_path, monkeypatch)
    flat = arr.ravel(order="K")
    assert np.shares_memory(flat, arr), "flatten copied the whole F-order memmap"
    # stats still works correctly on the F-order array
    st = array_stats(arr)
    assert st.finite_min == 0.0
    assert st.finite_max == float(arr.size - 1)


def test_finite_sample_does_not_copy_fortran_memmap(tmp_path, monkeypatch):
    arr = _fortran_memmap(tmp_path, monkeypatch)
    assert np.shares_memory(arr.ravel(order="K"), arr)
    finite, n_total, n_used = finite_sample(arr)
    assert n_total == arr.size
    assert finite.min() == 0.0


def test_sampled_flat_view_keeps_fortran_memmap_a_view(tmp_path, monkeypatch):
    arr = _fortran_memmap(tmp_path, monkeypatch)
    sample, n_total, n_used = limits.sampled_flat_view(arr, limits.HIST_MAX_SAMPLES)
    assert np.shares_memory(sample, arr), "sampled_flat_view copied the F-order memmap"
    assert n_total == arr.size
    assert n_used == arr.size  # within budget: full flat view, no subsampling


def test_sampled_flat_view_subsamples_over_budget():
    arr = np.arange(100, dtype=np.float64)
    sample, n_total, n_used = limits.sampled_flat_view(arr, budget=10)
    assert n_total == 100
    assert n_used < n_total  # stride > 1 once the element count exceeds budget


# ---------------------------------------------------------------------------
# stats.py — sampling
# ---------------------------------------------------------------------------

def test_array_stats_sampled_flag_and_approx_range(monkeypatch):
    # Sampling is gated on element count vs HIST_MAX_SAMPLES, not on bytes:
    # LARGE_BYTES stays at its (huge) default to prove the decoupling.
    monkeypatch.setattr(limits, "HIST_MAX_SAMPLES", 8)
    arr = np.arange(100, dtype=np.float32)
    st = array_stats(arr)
    assert st.sampled is True
    assert "(approx)" in st.range_str()
    assert st.finite_min is not None


def test_array_stats_sampled_anomaly_is_qualitative(monkeypatch):
    monkeypatch.setattr(limits, "HIST_MAX_SAMPLES", 50)
    arr = np.arange(100, dtype=np.float32)
    arr[::3] = np.nan
    st = array_stats(arr)
    assert st.sampled is True
    text = st.anomaly_str()
    assert "present in sample" in text
    assert not any(ch.isdigit() for ch in text)  # no count numbers


def test_array_stats_small_path_unchanged():
    arr = np.array([1.0, np.nan, 3.0], dtype=np.float32)
    st = array_stats(arr)
    assert st.sampled is False
    assert "NaN: 1" in st.anomaly_str()


# ---------------------------------------------------------------------------
# histogram.py — finite_sample + sampling label
# ---------------------------------------------------------------------------

def test_finite_sample_respects_budget(monkeypatch):
    monkeypatch.setattr(limits, "HIST_MAX_SAMPLES", 10)
    arr = np.arange(100, dtype=np.float32)
    finite, n_total, n_used = finite_sample(arr)
    assert n_total == 100
    assert n_used <= 10
    assert finite.size <= 10


def test_histogram_sample_label_visible_when_sampled(monkeypatch):
    monkeypatch.setattr(limits, "HIST_MAX_SAMPLES", 10)
    v = HistogramView()
    v.set_data(np.arange(100, dtype=np.float32))
    assert not v._sample_label.isHidden()
    assert "sampled" in v._sample_label.text()


def test_histogram_sample_label_hidden_when_small():
    v = HistogramView()
    v.set_data(np.arange(20, dtype=np.float32))
    assert v._sample_label.isHidden()


# ---------------------------------------------------------------------------
# image.py — downsampling
# ---------------------------------------------------------------------------

def test_image_downsamples_large_array(monkeypatch):
    # Downsampling is gated on spatial pixel count vs IMAGE_MAX_PIXELS, not on
    # bytes: LARGE_BYTES stays at its default to prove the decoupling.
    monkeypatch.setattr(limits, "IMAGE_MAX_PIXELS", 16)
    iv = ImageView()
    arr = np.arange(64, dtype=np.float32).reshape(8, 8)
    iv.set_data(arr)
    assert iv._canvas._stride > 1
    dh, dw = iv._canvas._disp.shape[:2]
    assert dh < 8 and dw < 8
    assert not iv._downsample_label.isHidden()
    assert "downsampled" in iv._downsample_label.text()


def test_image_no_downsample_when_small():
    iv = ImageView()
    iv.set_data(np.arange(64, dtype=np.float32).reshape(8, 8))
    assert iv._canvas._stride == 1
    assert iv._downsample_label.isHidden()


def test_image_hover_reads_full_resolution(monkeypatch):
    monkeypatch.setattr(limits, "IMAGE_MAX_PIXELS", 16)
    iv = ImageView()
    arr = np.arange(64, dtype=np.float32).reshape(8, 8)
    iv.set_data(arr)
    # full-resolution data retained for exact hover readout
    assert iv._canvas._data.shape == (8, 8)
    assert iv._canvas._data[7, 7] == arr[7, 7]


def test_image_profile_input_is_float(monkeypatch):
    """Display array handed to compute_profile is already float (no per-drag astype)."""
    monkeypatch.setattr(limits, "IMAGE_MAX_PIXELS", 16)
    iv = ImageView()
    iv.set_data(np.arange(64, dtype=np.float32).reshape(8, 8))
    assert np.issubdtype(iv._canvas._disp.dtype, np.floating)
