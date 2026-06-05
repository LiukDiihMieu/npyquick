from __future__ import annotations

import numpy as np
import pytest

from npyquick.model import NpyDataModel


def test_load_npy_available_arrays(tmp_path):
    arr = np.arange(12).reshape(3, 4).astype(np.float32)
    p = tmp_path / "a.npy"
    np.save(p, arr)
    m = NpyDataModel()
    m.load(str(p))
    metas = m.available_array_meta()
    assert list(metas.keys()) == [""]
    assert metas[""].shape == (3, 4)
    assert metas[""].dtype == np.float32


def test_load_npy_auto_selects_array(tmp_path):
    arr = np.zeros((5, 5), dtype=np.float64)
    p = tmp_path / "b.npy"
    np.save(p, arr)
    m = NpyDataModel()
    m.load(str(p))
    assert m.array is not None
    np.testing.assert_array_equal(m.array, arr)


def test_load_npz_available_arrays(tmp_path):
    a = np.ones((3, 3), dtype=np.float32)
    b = np.arange(6)
    p = tmp_path / "multi.npz"
    np.savez(p, x=a, y=b)
    m = NpyDataModel()
    m.load(str(p))
    metas = m.available_array_meta()
    assert set(metas.keys()) == {"x", "y"}
    assert metas["x"].shape == (3, 3)
    assert metas["x"].dtype == np.float32
    assert metas["y"].shape == (6,)


def test_load_npz_defers_selection(tmp_path):
    """load() must not materialize any member — that happens in select_array()."""
    p = tmp_path / "multi.npz"
    np.savez(p, x=np.ones(3), y=np.zeros(3))
    m = NpyDataModel()
    m.load(str(p))
    assert m.array is None
    assert m._selected_key == ""


def test_select_array_switches_active(tmp_path):
    a = np.ones((2, 2), dtype=np.float32)
    b = np.full((2, 2), 9.0, dtype=np.float32)
    p = tmp_path / "two.npz"
    np.savez(p, first=a, second=b)
    m = NpyDataModel()
    m.load(str(p))
    m.select_array("second")
    np.testing.assert_array_equal(m.array, b)
    assert m._selected_key == "second"


def test_select_array_invalid_key_raises(tmp_path):
    arr = np.zeros((3, 3))
    p = tmp_path / "c.npy"
    np.save(p, arr)
    m = NpyDataModel()
    m.load(str(p))
    with pytest.raises(KeyError):
        m.select_array("nonexistent")


def test_fresh_model_has_no_array():
    m = NpyDataModel()
    assert m.array is None
    assert m.available_array_meta() == {}


def test_path_set_after_load(tmp_path):
    p = tmp_path / "d.npy"
    np.save(p, np.zeros(5))
    m = NpyDataModel()
    m.load(str(p))
    assert m.path == str(p)


def test_empty_npz_raises_value_error(tmp_path):
    p = tmp_path / "empty.npz"
    np.savez(p)  # archive with no arrays
    m = NpyDataModel()
    with pytest.raises(ValueError, match="no arrays"):
        m.load(str(p))


def test_empty_npz_does_not_pollute_previous_state(tmp_path):
    good = tmp_path / "good.npy"
    np.save(good, np.arange(6, dtype=np.float32))
    empty_npz = tmp_path / "empty.npz"
    np.savez(empty_npz)

    m = NpyDataModel()
    m.load(str(good))
    prev_array = m.array
    prev_path = m.path

    with pytest.raises(ValueError):
        m.load(str(empty_npz))

    assert m.path == prev_path
    np.testing.assert_array_equal(m.array, prev_array)
