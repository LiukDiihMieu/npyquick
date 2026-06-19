"""Regression tests for edge-case inputs that previously caused crashes."""
from __future__ import annotations

import numpy as np
import pytest

from npyquick.app import _format_array_summary
from npyquick.views.image import ImageView
from npyquick.views.table import NpyTableModel


# ---------------------------------------------------------------------------
# _format_array_summary
# ---------------------------------------------------------------------------

def test_summary_empty_row():
    s = _format_array_summary(np.empty((0, 5)))
    assert "empty" in s
    assert "range" not in s


def test_summary_empty_col():
    s = _format_array_summary(np.zeros((5, 0)))
    assert "empty" in s
    assert "range" not in s


def test_summary_empty_2d():
    s = _format_array_summary(np.empty((0, 0)))
    assert "empty" in s


def test_summary_scalar_shows_range():
    s = _format_array_summary(np.array(3.14))
    assert "range" in s
    assert "empty" not in s


def test_summary_normal_numeric():
    s = _format_array_summary(np.array([[1.0, 2.0], [3.0, 4.0]]))
    assert "range [1" in s


def test_summary_non_numeric_no_range():
    s = _format_array_summary(np.array(["hello", "world"]))
    assert "range" not in s
    assert "empty" not in s


# ---------------------------------------------------------------------------
# NpyTableModel — scalar (ndim == 0)
# ---------------------------------------------------------------------------

def test_table_model_scalar_is_1x1():
    m = NpyTableModel()
    m.set_array(np.array(3.14))
    assert m.rowCount() == 1
    assert m.columnCount() == 1


def test_table_model_scalar_data_is_value():
    from PySide6.QtCore import QModelIndex, Qt
    m = NpyTableModel()
    m.set_array(np.array(42.0))
    idx = m.index(0, 0)
    assert float(m.data(idx, Qt.DisplayRole)) == pytest.approx(42.0)


# ---------------------------------------------------------------------------
# ImageView.can_handle — 2D complex is shown as a dual real/imag panel; complex
# RGB is not supported (falls through to the Table view).
# (Empty-array rejection lives in test_image_canvas.py alongside the rest of
# the can_handle coverage.)
# ---------------------------------------------------------------------------

def test_image_accepts_complex_2d():
    assert ImageView.can_handle(np.zeros((4, 4), dtype=np.complex128)) is True


def test_image_rejects_complex_rgb():
    assert ImageView.can_handle(np.zeros((4, 4, 3), dtype=np.complex64)) is False


# ---------------------------------------------------------------------------
# Complex arrays fall back to Table view only
# ---------------------------------------------------------------------------

def test_table_accepts_complex():
    from npyquick.views.table import RawTableView
    assert RawTableView.can_handle(np.zeros((4, 4), dtype=np.complex128)) is True


def test_table_shows_complex_anomaly():
    from npyquick.views.table import RawTableView
    arr = np.array([[complex(np.nan, 0), 1 + 1j], [2 + 2j, complex(0, np.inf)]],
                   dtype=np.complex128)
    tv = RawTableView()
    tv.set_data(arr)
    assert "NaN: 1" in tv._info.text() and "+Inf: 1" in tv._info.text()
