"""Tests for .npz array picker UI in MainWindow."""
from __future__ import annotations

import numpy as np


def test_array_bar_hidden_after_npy(main_window, write_npy):
    main_window.load_file(write_npy(np.zeros((10, 10), dtype=np.float32)))
    assert main_window._array_bar.isHidden()


def test_array_bar_visible_for_single_array_npz(main_window, write_npz):
    """Single-member .npz should also show the picker so the ceiling check fires
    at selection time, not at open time."""
    main_window.load_file(write_npz(data=np.zeros((10, 10), dtype=np.float32)))
    assert not main_window._array_bar.isHidden()
    assert main_window._array_combo.count() == 1
    assert main_window._model.array is None  # not yet materialized


def test_array_bar_visible_for_multi_array_npz(main_window, write_npz):
    main_window.load_file(write_npz(
        image=np.zeros((10, 10), dtype=np.float32),
        mask=np.ones((10, 10), dtype=np.uint8),
    ))
    assert not main_window._array_bar.isHidden()
    assert main_window._array_combo.count() == 2


def test_combo_items_contain_key_and_shape(main_window, write_npz):
    main_window.load_file(write_npz(
        alpha=np.zeros((4, 5), dtype=np.float32),
        beta=np.ones((3,), dtype=np.int16),
    ))
    texts = [
        main_window._array_combo.itemText(i)
        for i in range(main_window._array_combo.count())
    ]
    assert any("alpha" in t and "4" in t and "5" in t for t in texts)
    assert any("beta" in t and "3" in t for t in texts)


def test_combo_userdata_is_key(main_window, write_npz):
    main_window.load_file(write_npz(
        x=np.zeros((2, 2)),
        y=np.ones((3, 3)),
    ))
    keys = {
        main_window._array_combo.itemData(i)
        for i in range(main_window._array_combo.count())
    }
    assert keys == {"x", "y"}


def test_selecting_combo_item_switches_model_array(main_window, write_npz):
    arr_x = np.full((4, 4), 1.0, dtype=np.float32)
    arr_y = np.full((6, 6), 2.0, dtype=np.float32)
    main_window.load_file(write_npz(x=arr_x, y=arr_y))

    # Simulate user picking 'y' — use activated signal (user-driven), not
    # setCurrentIndex (programmatic, does not trigger activated).
    for i in range(main_window._array_combo.count()):
        if main_window._array_combo.itemData(i) == "y":
            main_window._array_combo.activated.emit(i)
            break

    assert main_window._model.array.shape == (6, 6)
    np.testing.assert_array_equal(main_window._model.array, arr_y)


def test_first_combo_item_loads_on_first_pick(main_window, write_npz):
    """Regression: selecting the first npz member (index 0) must load it even
    though the combo starts at index -1 (no pre-selection after open)."""
    arr_a = np.full((5, 5), 3.0, dtype=np.float32)
    arr_b = np.ones((3, 3), dtype=np.float32)
    main_window.load_file(write_npz(a=arr_a, b=arr_b))

    assert main_window._array_combo.currentIndex() == -1   # no item pre-selected
    assert main_window._model.array is None

    # simulate user picking the first item (index 0) via activated
    main_window._array_combo.activated.emit(0)
    assert main_window._model.array is not None
