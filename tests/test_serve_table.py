# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 LiukDiihMieu

"""Framework-neutral tests for npyquick.serve.views.table's pure helpers —
no NiceGUI element/browser involved, per AG_GRID_REPLACEMENT_PLAN.md's
guidance to keep this migration's coverage runnable as ordinary Python
unit tests."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("nicegui")

from npyquick.core import limits  # noqa: E402
from npyquick.serve.views.table import (  # noqa: E402
    _SERVE_TABLE_MAX_PER_AXIS,
    _format_cell,
    _prepare_table_array,
    _table_columns,
    _table_rows,
    _too_large_to_tabulate_message,
)


# ----------------------------------------------------------------------
# _prepare_table_array: scalar / 1-D / 2-D / high-dimensional reshape
# ----------------------------------------------------------------------

def test_scalar_array_becomes_1x1():
    arr2d, flat, message = _prepare_table_array(np.array(7))
    assert message == ""
    assert flat is False
    assert arr2d.shape == (1, 1)
    assert arr2d[0, 0] == 7


def test_1d_array_stays_flat():
    arr2d, flat, message = _prepare_table_array(np.arange(5))
    assert message == ""
    assert flat is True
    assert arr2d.shape == (5,)


def test_2d_array_passes_through_unchanged():
    a = np.zeros((10, 7))
    arr2d, flat, message = _prepare_table_array(a)
    assert message == ""
    assert flat is False
    assert arr2d is a


def test_high_dim_c_contiguous_reshapes_to_last_axis_cols():
    a = np.arange(4 * 5 * 6).reshape(4, 5, 6)
    arr2d, flat, message = _prepare_table_array(a)
    assert message == ""
    assert flat is False
    assert arr2d.shape == (20, 6)


def test_large_fortran_order_array_is_refused(monkeypatch):
    monkeypatch.setattr(limits, "LARGE_BYTES", 0)  # everything counts as large
    a = np.asfortranarray(np.arange(4 * 5 * 6).reshape(4, 5, 6))
    assert not a.flags["C_CONTIGUOUS"]
    arr2d, flat, message = _prepare_table_array(a)
    assert arr2d is None
    assert message != ""
    assert "Fortran" in message


def test_large_c_contiguous_array_is_not_refused(monkeypatch):
    monkeypatch.setattr(limits, "LARGE_BYTES", 0)
    a = np.arange(4 * 5 * 6).reshape(4, 5, 6)  # C-contiguous by construction
    arr2d, flat, message = _prepare_table_array(a)
    assert message == ""
    assert arr2d is not None


def test_small_fortran_order_array_is_not_refused():
    # Below LARGE_BYTES (the real, un-monkeypatched threshold) -- refusal is
    # about avoiding a copy of a genuinely large memmap, not Fortran order
    # by itself.
    a = np.asfortranarray(np.arange(4 * 5 * 6).reshape(4, 5, 6))
    arr2d, flat, message = _prepare_table_array(a)
    assert message == ""
    assert arr2d is not None


def test_too_large_message_mentions_shape_and_histogram_fallback():
    a = np.zeros((3, 4, 5))
    msg = _too_large_to_tabulate_message(a)
    assert "3-D" in msg
    assert "Histogram" in msg


# ----------------------------------------------------------------------
# _format_cell: floats, ints, complex, strings, structured
# ----------------------------------------------------------------------

def test_format_cell_float_uses_6g():
    assert _format_cell(np.float64(1.0 / 3.0)) == "0.333333"
    assert _format_cell(1.0 / 3.0) == "0.333333"


def test_format_cell_int_uses_str():
    assert _format_cell(np.int64(42)) == "42"
    assert _format_cell(42) == "42"


def test_format_cell_complex_uses_str():
    val = np.complex128(1 + 2j)
    assert _format_cell(val) == str(val)


def test_format_cell_string_uses_str():
    assert _format_cell(np.str_("hello")) == "hello"


def test_format_cell_structured_scalar_uses_str():
    a = np.array([(1, "a")], dtype=[("x", "i4"), ("y", "U1")])
    assert _format_cell(a[0]) == str(a[0])


# ----------------------------------------------------------------------
# _table_columns / _table_rows: QTable column/row shape, row indices
# ----------------------------------------------------------------------

def test_table_columns_leads_with_sticky_idx_column():
    columns = _table_columns(3, data_width=70)
    assert columns[0]["name"] == "_idx"
    assert columns[0]["classes"] == "npyquick-idx-col"
    assert [c["name"] for c in columns[1:]] == ["0", "1", "2"]


def test_table_columns_data_width_applied_to_data_columns_only():
    columns = _table_columns(2, data_width=123)
    assert "123px" in columns[1]["style"]
    assert "123px" not in columns[0]["style"]


def test_table_rows_2d_includes_row_index_and_formatted_values():
    a = np.array([[1.0, 2.0], [3.0, 4.0]])
    rows = _table_rows(a, flat=False)
    assert rows == [
        {"_idx": 0, "0": "1", "1": "2"},
        {"_idx": 1, "0": "3", "1": "4"},
    ]


def test_table_rows_flat_uses_single_data_column_named_0():
    a = np.array([10, 20, 30])
    rows = _table_rows(a, flat=True)
    assert rows == [
        {"_idx": 0, "0": "10"},
        {"_idx": 1, "0": "20"},
        {"_idx": 2, "0": "30"},
    ]


def test_table_rows_row_indices_are_sequential_even_after_slicing():
    # Mirrors how set_data() calls this on an already-truncated/sliced sub-
    # array: _idx must count from 0 over the SLICE, not carry the original
    # array's absolute row numbers.
    a = np.arange(20).reshape(10, 2)[3:6]
    rows = _table_rows(a, flat=False)
    assert [r["_idx"] for r in rows] == [0, 1, 2]


# ----------------------------------------------------------------------
# RGB channel slicing (mirrors TableView.set_data()'s RGB branch)
# ----------------------------------------------------------------------

def test_rgb_channels_slice_independently():
    a = np.arange(2 * 3 * 3).reshape(2, 3, 3)
    r, g, b = (_table_rows(a[:, :, i], flat=False) for i in range(3))
    assert r != g
    assert g != b
    # Same row/col structure across channels, different data
    assert [set(row) for row in r] == [set(row) for row in g]


# ----------------------------------------------------------------------
# The 512-per-axis cap (via full set_data(), not just the pure helpers)
# ----------------------------------------------------------------------

def test_serve_cap_is_512_per_axis():
    assert _SERVE_TABLE_MAX_PER_AXIS == 512
