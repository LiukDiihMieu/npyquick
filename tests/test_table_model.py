from __future__ import annotations

import numpy as np

from npyquick.views.table import NpyTableModel


def test_1d_array_is_single_column():
    m = NpyTableModel()
    m.set_array(np.arange(5))
    assert m.rowCount() == 5
    assert m.columnCount() == 1


def test_2d_array_shape():
    m = NpyTableModel()
    m.set_array(np.zeros((10, 7)))
    assert m.rowCount() == 10
    assert m.columnCount() == 7


def test_3d_array_reshapes_to_last_axis_cols():
    m = NpyTableModel()
    m.set_array(np.zeros((4, 5, 6)))
    # reshape(-1, 6) → (20, 6)
    assert m.rowCount() == 20
    assert m.columnCount() == 6


def test_row_cap_applied():
    m = NpyTableModel()
    m.set_array(np.zeros((NpyTableModel.MAX_ROWS + 100, 5)))
    assert m.rowCount() == NpyTableModel.MAX_ROWS


def test_col_cap_applied():
    m = NpyTableModel()
    m.set_array(np.zeros((5, NpyTableModel.MAX_COLS + 100)))
    assert m.columnCount() == NpyTableModel.MAX_COLS


def test_set_array_replaces_previous():
    m = NpyTableModel()
    m.set_array(np.zeros((3, 4)))
    m.set_array(np.zeros((7, 2)))
    assert m.rowCount() == 7
    assert m.columnCount() == 2
