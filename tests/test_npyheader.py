from __future__ import annotations

import numpy as np

from npyquick.core.npyheader import peek_npy, peek_npz, read_npy_header


def test_read_npy_header_from_stream(tmp_path):
    arr = np.zeros((5, 7), dtype=np.float64)
    p = tmp_path / "a.npy"
    np.save(p, arr)
    with open(p, "rb") as fp:
        shape, dtype = read_npy_header(fp)
    assert shape == (5, 7)
    assert dtype == np.float64


def test_peek_npy_metadata(tmp_path):
    arr = np.zeros((4, 4, 3), dtype=np.uint8)
    p = tmp_path / "rgb.npy"
    np.save(p, arr)
    meta = peek_npy(str(p))
    assert meta.shape == (4, 4, 3)
    assert meta.dtype == np.uint8
    assert meta.nbytes == arr.nbytes
    assert meta.compressed is False


def test_peek_npy_zero_d(tmp_path):
    p = tmp_path / "scalar.npy"
    np.save(p, np.array(3.5))
    meta = peek_npy(str(p))
    assert meta.shape == ()
    assert meta.nbytes == 8


def test_peek_npz_uncompressed(tmp_path):
    p = tmp_path / "u.npz"
    np.savez(p, x=np.ones((2, 3), np.float32), y=np.arange(5, dtype=np.int16))
    metas = peek_npz(str(p))
    assert set(metas) == {"x", "y"}
    assert metas["x"].shape == (2, 3)
    assert metas["x"].dtype == np.float32
    assert metas["x"].compressed is False
    assert metas["y"].shape == (5,)


def test_peek_npz_compressed_flag(tmp_path):
    p = tmp_path / "c.npz"
    np.savez_compressed(p, big=np.zeros((10, 10), np.float32))
    metas = peek_npz(str(p))
    assert metas["big"].shape == (10, 10)
    assert metas["big"].compressed is True


def test_peek_npz_keys_match_npzfile(tmp_path):
    """Dropdown keys must match what np.load()[key] expects."""
    p = tmp_path / "k.npz"
    np.savez(p, alpha=np.zeros(3), beta=np.ones(4))
    metas = peek_npz(str(p))
    with np.load(str(p)) as f:
        for key in metas:
            assert f[key].shape == metas[key].shape
