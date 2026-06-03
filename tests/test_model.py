from __future__ import annotations

import numpy as np

from npyquick.model import NpyDataModel


def test_empty_model_has_no_views():
    assert NpyDataModel().compatible_views() == []


def test_2d_numeric_supports_image():
    m = NpyDataModel()
    m.array = np.zeros((10, 12), dtype=np.float32)
    views = m.compatible_views()
    assert "image" in views
    assert "table" in views


def test_rgb_h_w_3_supports_image():
    m = NpyDataModel()
    m.array = np.zeros((10, 12, 3), dtype=np.uint8)
    assert "image" in m.compatible_views()


def test_rgba_not_supported_as_image():
    m = NpyDataModel()
    m.array = np.zeros((10, 12, 4), dtype=np.uint8)
    views = m.compatible_views()
    assert "image" not in views
    assert "table" in views


def test_1d_not_supported_as_image():
    m = NpyDataModel()
    m.array = np.arange(10)
    views = m.compatible_views()
    assert "image" not in views
    assert "table" in views


def test_3d_non_rgb_not_supported_as_image():
    m = NpyDataModel()
    m.array = np.zeros((5, 10, 10), dtype=np.float64)
    views = m.compatible_views()
    assert "image" not in views
    assert "table" in views


def test_bool_2d_not_supported_as_image():
    m = NpyDataModel()
    m.array = np.zeros((10, 10), dtype=bool)
    assert "image" not in m.compatible_views()
    assert "table" in m.compatible_views()


def test_table_always_present_when_array_set():
    m = NpyDataModel()
    for arr in [
        np.arange(5),
        np.zeros((3, 4)),
        np.zeros((3, 4, 5)),
        np.array(["a", "b"]),
    ]:
        m.array = arr
        assert "table" in m.compatible_views()
