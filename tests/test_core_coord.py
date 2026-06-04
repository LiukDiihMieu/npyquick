from __future__ import annotations

import numpy as np
import pytest

from npyquick.core.coord import PixelTransform


def test_default_is_identity():
    t = PixelTransform()
    assert t.pixel_size == 1.0
    assert t.unit == "None"
    np.testing.assert_array_equal(t.to_pixel([3.0, 4.0]), [3.0, 4.0])
    np.testing.assert_array_equal(t.to_physical([3.0, 4.0]), [3.0, 4.0])


def test_extent_with_unit_ps():
    t = PixelTransform()
    ext = t.extent(h=10, w=20)
    assert ext == [-0.5, 19.5, 9.5, -0.5]


def test_extent_scales_with_ps():
    t = PixelTransform(pixel_size=0.5, unit="μm")
    ext = t.extent(h=10, w=20)
    assert ext == [-0.25, 9.75, 4.75, -0.25]


def test_to_pixel_and_back_roundtrip():
    t = PixelTransform(pixel_size=2.5, unit="mm")
    physical = np.array([5.0, 7.5])
    pixel = t.to_pixel(physical)
    np.testing.assert_allclose(pixel, [2.0, 3.0])
    np.testing.assert_allclose(t.to_physical(pixel), physical)


def test_clamp_x_physical_clamps_to_extent():
    t = PixelTransform(pixel_size=2.0, unit="μm")
    # x bounds for w=10: [-1.0, 19.0]
    assert t.clamp_x_physical(-100.0, w=10) == -1.0
    assert t.clamp_x_physical(100.0, w=10) == 19.0
    assert t.clamp_x_physical(5.0, w=10) == 5.0


def test_clamp_y_physical_clamps_to_extent():
    t = PixelTransform(pixel_size=2.0, unit="μm")
    # y bounds for h=8: [-1.0, 15.0]
    assert t.clamp_y_physical(-100.0, h=8) == -1.0
    assert t.clamp_y_physical(100.0, h=8) == 15.0


def test_format_unit_hides_none():
    assert PixelTransform(pixel_size=1.0, unit="None").format_unit() == ""
    assert PixelTransform(pixel_size=0.5, unit="μm").format_unit() == "μm"
    assert PixelTransform(pixel_size=2.0, unit="mm").format_unit() == "mm"


def test_equality_is_value_based():
    a = PixelTransform(pixel_size=0.5, unit="μm")
    b = PixelTransform(pixel_size=0.5, unit="μm")
    c = PixelTransform(pixel_size=0.5, unit="mm")
    d = PixelTransform(pixel_size=1.0, unit="μm")
    assert a == b
    assert a != c
    assert a != d


def test_frozen_dataclass_is_immutable():
    t = PixelTransform()
    with pytest.raises(Exception):
        t.pixel_size = 2.0   # type: ignore[misc]
