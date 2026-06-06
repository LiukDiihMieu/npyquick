from __future__ import annotations

import numpy as np
from PySide6.QtCore import QModelIndex, Qt

from npyquick.core import limits
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
    m.set_array(np.zeros((limits.TABLE_MAX_PER_AXIS + 100, 5)))
    assert m.rowCount() == limits.TABLE_MAX_PER_AXIS


def test_col_cap_applied():
    m = NpyTableModel()
    m.set_array(np.zeros((5, limits.TABLE_MAX_PER_AXIS + 100)))
    assert m.columnCount() == limits.TABLE_MAX_PER_AXIS


def test_set_array_replaces_previous():
    m = NpyTableModel()
    m.set_array(np.zeros((3, 4)))
    m.set_array(np.zeros((7, 2)))
    assert m.rowCount() == 7
    assert m.columnCount() == 2


# ---------------------------------------------------------------------------
# data() — cell value contract
# ---------------------------------------------------------------------------

def test_data_returns_correct_2d_int_cell():
    m = NpyTableModel()
    arr = np.arange(20, dtype=np.int32).reshape(4, 5)
    m.set_array(arr)
    # arr[1, 2] == 7
    assert m.data(m.index(1, 2), Qt.DisplayRole) == "7"


def test_data_2d_float_uses_6_significant_digits():
    # The model formats floats with "%.6g" so very long decimals are truncated
    # without losing precision for typical values.
    m = NpyTableModel()
    arr = np.array([[1.0 / 3.0, 2.5], [1e-9, 12345678.0]], dtype=np.float64)
    m.set_array(arr)
    assert m.data(m.index(0, 0), Qt.DisplayRole) == f"{1.0 / 3.0:.6g}"
    assert m.data(m.index(1, 1), Qt.DisplayRole) == f"{12345678.0:.6g}"


def test_data_1d_uses_single_column_indexing():
    m = NpyTableModel()
    m.set_array(np.array([10, 20, 30], dtype=np.int32))
    assert m.data(m.index(2, 0), Qt.DisplayRole) == "30"


def test_data_3d_reshape_is_c_order():
    # (4, 5, 6) flattens to (20, 6) in C-order: row r corresponds to (r // 5,
    # r % 5). Cell (7, 2) therefore reads array[1, 2, 2].
    m = NpyTableModel()
    arr = np.arange(120, dtype=np.int32).reshape(4, 5, 6)
    m.set_array(arr)
    assert m.data(m.index(7, 2), Qt.DisplayRole) == str(arr[1, 2, 2])


def test_data_structured_dtype_returns_string_per_record():
    # Structured dtypes are treated as 1D record rows; data() must stringify
    # the record without crashing.
    m = NpyTableModel()
    arr = np.array(
        [("alpha", 1.5), ("beta", 2.5)],
        dtype=[("name", "U10"), ("val", "f4")],
    )
    m.set_array(arr)
    text = m.data(m.index(0, 0), Qt.DisplayRole)
    assert isinstance(text, str)
    assert "alpha" in text and "1.5" in text


def test_data_returns_none_for_invalid_index():
    m = NpyTableModel()
    m.set_array(np.zeros((3, 3)))
    assert m.data(QModelIndex(), Qt.DisplayRole) is None


def test_data_returns_none_for_non_display_role():
    m = NpyTableModel()
    m.set_array(np.zeros((3, 3)))
    assert m.data(m.index(0, 0), Qt.ToolTipRole) is None


def test_data_returns_none_when_no_array_set():
    m = NpyTableModel()
    assert m.data(m.index(0, 0), Qt.DisplayRole) is None


# ---------------------------------------------------------------------------
# headerData()
# ---------------------------------------------------------------------------

def test_header_data_is_section_index():
    m = NpyTableModel()
    m.set_array(np.zeros((3, 4)))
    assert m.headerData(0, Qt.Horizontal, Qt.DisplayRole) == "0"
    assert m.headerData(2, Qt.Vertical, Qt.DisplayRole) == "2"


def test_header_data_returns_none_for_non_display_role():
    m = NpyTableModel()
    m.set_array(np.zeros((3, 4)))
    assert m.headerData(0, Qt.Horizontal, Qt.ToolTipRole) is None
