"""Tests for core/stats.py and NaN/Inf display in views."""
from __future__ import annotations

import numpy as np
import pytest

from npyquick.app import _format_array_summary
from npyquick.core.stats import ArrayStats, array_stats, is_real_numeric
from npyquick.views.image import ImageView


# ---------------------------------------------------------------------------
# array_stats — pure logic
# ---------------------------------------------------------------------------

def test_is_real_numeric_float():
    assert is_real_numeric(np.zeros(3, dtype=np.float64))

def test_is_real_numeric_int():
    assert is_real_numeric(np.zeros(3, dtype=np.int32))

def test_is_real_numeric_rejects_complex():
    assert not is_real_numeric(np.zeros(3, dtype=np.complex128))

def test_is_real_numeric_rejects_string():
    assert not is_real_numeric(np.array(["a", "b"]))

def test_array_stats_complex_finite_has_no_range_or_anomaly():
    arr = np.array([1+2j, 3+4j], dtype=np.complex128)
    s = array_stats(arr)
    assert s is not None
    assert s.complex_dtype is True
    assert s.finite_min is None and s.finite_max is None
    assert not s.has_anomaly
    assert s.range_str() == ""  # complex has no single ordered range

def test_array_stats_complex_splits_pos_neg_inf():
    arr = np.array([complex(np.nan, 0), complex(np.inf, 1), complex(1, -np.inf)],
                   dtype=np.complex128)
    s = array_stats(arr)
    assert (s.nan_count, s.pos_inf_count, s.neg_inf_count) == (1, 1, 1)
    assert s.anomaly_str() == "NaN: 1  +Inf: 1  -Inf: 1"


def test_summary_shows_complex_anomaly_without_range():
    # The status bar (shown on every tab, incl. Table) must surface complex
    # anomalies the same way as real arrays, and not claim "no finite values".
    arr = np.array([[complex(np.nan, 0), 1 + 1j], [2 + 2j, complex(np.inf, 0)]],
                   dtype=np.complex128)
    summary = _format_array_summary(arr)
    assert "NaN: 1" in summary and "+Inf: 1" in summary
    assert "no finite values" not in summary

    clean = _format_array_summary(np.array([1 + 2j, 3 + 4j], dtype=np.complex128))
    assert "no finite values" not in clean and "NaN" not in clean


def test_integer_array_no_anomaly():
    s = array_stats(np.array([1, 2, 3], dtype=np.int32))
    assert s is not None
    assert not s.has_anomaly
    assert s.finite_min == 1.0
    assert s.finite_max == 3.0
    assert s.nan_count == 0


def test_float_clean_no_anomaly():
    s = array_stats(np.array([1.0, 2.0, 3.0], dtype=np.float32))
    assert s is not None
    assert not s.has_anomaly
    assert s.finite_min == pytest.approx(1.0)
    assert s.finite_max == pytest.approx(3.0)


def test_float_with_nan():
    arr = np.array([np.nan, 1.0, 2.0])
    s = array_stats(arr)
    assert s.nan_count == 1
    assert s.pos_inf_count == 0
    assert s.finite_min == pytest.approx(1.0)
    assert s.finite_max == pytest.approx(2.0)
    assert s.has_anomaly


def test_float_with_pos_inf():
    arr = np.array([1.0, np.inf, 2.0])
    s = array_stats(arr)
    assert s.pos_inf_count == 1
    assert s.nan_count == 0
    assert s.finite_min == pytest.approx(1.0)
    assert s.finite_max == pytest.approx(2.0)


def test_float_with_neg_inf():
    arr = np.array([-np.inf, 1.0, 2.0])
    s = array_stats(arr)
    assert s.neg_inf_count == 1
    assert s.finite_min == pytest.approx(1.0)


def test_float_mixed_anomalies():
    arr = np.array([np.nan, np.inf, -np.inf, 5.0])
    s = array_stats(arr)
    assert s.nan_count == 1
    assert s.pos_inf_count == 1
    assert s.neg_inf_count == 1
    assert s.finite_min == pytest.approx(5.0)
    assert s.finite_max == pytest.approx(5.0)


def test_all_nan_returns_none_range():
    arr = np.array([np.nan, np.nan])
    s = array_stats(arr)
    assert s.finite_min is None
    assert s.finite_max is None
    assert s.nan_count == 2
    assert s.has_anomaly


def test_all_inf():
    arr = np.array([np.inf, np.inf])
    s = array_stats(arr)
    assert s.finite_min is None
    assert s.pos_inf_count == 2


def test_non_numeric_returns_none():
    assert array_stats(np.array(["a", "b"])) is None


def test_empty_array_returns_none():
    assert array_stats(np.empty((0, 5))) is None


# ---------------------------------------------------------------------------
# ArrayStats.anomaly_str and range_str
# ---------------------------------------------------------------------------

def test_anomaly_str_only_nonzero():
    s = ArrayStats(1.0, 2.0, nan_count=3, pos_inf_count=0, neg_inf_count=1)
    assert "NaN: 3" in s.anomaly_str()
    assert "+Inf" not in s.anomaly_str()
    assert "-Inf: 1" in s.anomaly_str()


def test_anomaly_str_empty_when_clean():
    s = ArrayStats(1.0, 2.0, 0, 0, 0)
    assert s.anomaly_str() == ""


def test_range_str_prefix_with_anomaly():
    s = ArrayStats(1.0, 2.0, nan_count=1, pos_inf_count=0, neg_inf_count=0)
    assert s.range_str().startswith("finite range")


def test_range_str_prefix_without_anomaly():
    s = ArrayStats(1.0, 2.0, 0, 0, 0)
    assert s.range_str().startswith("range")
    assert "finite" not in s.range_str()


def test_range_str_no_finite_values():
    s = ArrayStats(None, None, nan_count=5, pos_inf_count=0, neg_inf_count=0)
    assert s.range_str() == "no finite values"


# ---------------------------------------------------------------------------
# _format_array_summary integration
# ---------------------------------------------------------------------------

def test_summary_with_nan_shows_finite_range():
    arr = np.array([np.nan, 1.0, 2.0])
    s = _format_array_summary(arr)
    assert "finite range" in s
    assert "NaN: 1" in s


def test_summary_all_nan():
    arr = np.array([np.nan, np.nan])
    s = _format_array_summary(arr)
    assert "no finite values" in s
    assert "NaN: 2" in s


def test_summary_clean_no_finite_prefix():
    arr = np.array([1.0, 2.0, 3.0])
    s = _format_array_summary(arr)
    assert "range" in s
    assert "finite range" not in s
    assert "NaN" not in s


# ---------------------------------------------------------------------------
# ImageView — anomaly_label visibility
# ---------------------------------------------------------------------------

def test_anomaly_label_hidden_for_clean_image():
    iv = ImageView()
    iv.set_data(np.zeros((8, 8), dtype=np.float32))
    assert iv._anomaly_label.isHidden()


def test_anomaly_label_shown_for_nan_image():
    iv = ImageView()
    arr = np.zeros((8, 8), dtype=np.float32)
    arr[0, 0] = np.nan
    iv.set_data(arr)
    assert not iv._anomaly_label.isHidden()
    assert "NaN: 1" in iv._anomaly_label.text()


def test_anomaly_label_shown_for_inf_image():
    iv = ImageView()
    arr = np.zeros((8, 8), dtype=np.float32)
    arr[1, 1] = np.inf
    iv.set_data(arr)
    assert not iv._anomaly_label.isHidden()
    assert "+Inf: 1" in iv._anomaly_label.text()


# ---------------------------------------------------------------------------
# ImageCanvas.reset_clim — all-NaN is a no-op
# ---------------------------------------------------------------------------

def test_reset_clim_with_all_nan_is_noop():
    iv = ImageView()
    arr = np.full((8, 8), np.nan, dtype=np.float32)
    iv.set_data(arr)
    # Should not raise; clim stays at matplotlib default
    iv._reset_clim()


def test_reset_clim_with_nan_uses_finite_range():
    iv = ImageView()
    arr = np.array([[1.0, np.nan], [2.0, np.inf]], dtype=np.float32)
    iv.set_data(arr)
    iv._reset_clim()
    vmin, vmax = iv._canvas._im.get_clim()
    assert vmin == pytest.approx(1.0)
    assert vmax == pytest.approx(2.0)
