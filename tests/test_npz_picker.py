"""Tests for .npz array picker UI in MainWindow."""
from __future__ import annotations

import numpy as np
import pytest

from npyquick.app import MainWindow


@pytest.fixture()
def win():
    w = MainWindow()
    return w


def _write_npz(tmp_path, **arrays):
    p = tmp_path / "test.npz"
    np.savez(str(p), **arrays)
    return str(p)


def _write_npy(tmp_path, array):
    p = tmp_path / "test.npy"
    np.save(str(p), array)
    return str(p)


def test_array_bar_hidden_after_npy(win, tmp_path):
    path = _write_npy(tmp_path, np.zeros((10, 10), dtype=np.float32))
    win.load_file(path)
    assert win._array_bar.isHidden()


def test_array_bar_visible_for_single_array_npz(win, tmp_path):
    """Single-member .npz should also show the picker so the ceiling check fires
    at selection time, not at open time."""
    path = _write_npz(tmp_path, data=np.zeros((10, 10), dtype=np.float32))
    win.load_file(path)
    assert not win._array_bar.isHidden()
    assert win._array_combo.count() == 1
    assert win._model.array is None  # not yet materialized


def test_array_bar_visible_for_multi_array_npz(win, tmp_path):
    path = _write_npz(
        tmp_path,
        image=np.zeros((10, 10), dtype=np.float32),
        mask=np.ones((10, 10), dtype=np.uint8),
    )
    win.load_file(path)
    assert not win._array_bar.isHidden()
    assert win._array_combo.count() == 2


def test_combo_items_contain_key_and_shape(win, tmp_path):
    path = _write_npz(
        tmp_path,
        alpha=np.zeros((4, 5), dtype=np.float32),
        beta=np.ones((3,), dtype=np.int16),
    )
    win.load_file(path)
    texts = [win._array_combo.itemText(i) for i in range(win._array_combo.count())]
    assert any("alpha" in t and "4" in t and "5" in t for t in texts)
    assert any("beta" in t and "3" in t for t in texts)


def test_combo_userdata_is_key(win, tmp_path):
    path = _write_npz(
        tmp_path,
        x=np.zeros((2, 2)),
        y=np.ones((3, 3)),
    )
    win.load_file(path)
    keys = {win._array_combo.itemData(i) for i in range(win._array_combo.count())}
    assert keys == {"x", "y"}


def test_selecting_combo_item_switches_model_array(win, tmp_path):
    arr_x = np.full((4, 4), 1.0, dtype=np.float32)
    arr_y = np.full((6, 6), 2.0, dtype=np.float32)
    path = _write_npz(tmp_path, x=arr_x, y=arr_y)
    win.load_file(path)

    # Simulate user picking 'y' — use activated signal (user-driven), not
    # setCurrentIndex (programmatic, does not trigger activated).
    for i in range(win._array_combo.count()):
        if win._array_combo.itemData(i) == "y":
            win._array_combo.activated.emit(i)
            break

    assert win._model.array.shape == (6, 6)
    np.testing.assert_array_equal(win._model.array, arr_y)


def test_first_combo_item_loads_on_first_pick(win, tmp_path):
    """Regression: selecting the first npz member (index 0) must load it even
    though the combo starts at index -1 (no pre-selection after open)."""
    arr_a = np.full((5, 5), 3.0, dtype=np.float32)
    arr_b = np.ones((3, 3), dtype=np.float32)
    path = _write_npz(tmp_path, a=arr_a, b=arr_b)
    win.load_file(path)

    assert win._array_combo.currentIndex() == -1   # no item pre-selected
    assert win._model.array is None

    # simulate user picking the first item (index 0) via activated
    win._array_combo.activated.emit(0)
    assert win._model.array is not None
