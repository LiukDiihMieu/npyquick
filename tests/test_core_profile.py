from __future__ import annotations

import numpy as np

from npyquick.core.profile import compute_profile


def test_2d_horizontal_line_recovers_row():
    arr = np.arange(100, dtype=float).reshape(10, 10)
    # horizontal line y=5, x from 0 to 9
    p0 = np.array([0.0, 5.0])
    p1 = np.array([9.0, 5.0])
    dists, values = compute_profile(arr, p0, p1)
    np.testing.assert_allclose(values, arr[5, :], atol=1e-6)
    np.testing.assert_allclose(dists[0], 0.0)
    np.testing.assert_allclose(dists[-1], 9.0)


def test_2d_vertical_line_recovers_column():
    arr = np.arange(100, dtype=float).reshape(10, 10)
    p0 = np.array([3.0, 0.0])
    p1 = np.array([3.0, 9.0])
    _, values = compute_profile(arr, p0, p1)
    np.testing.assert_allclose(values, arr[:, 3], atol=1e-6)


def test_2d_diagonal_length():
    arr = np.zeros((10, 10), dtype=float)
    p0 = np.array([0.0, 0.0])
    p1 = np.array([9.0, 9.0])
    dists, _ = compute_profile(arr, p0, p1)
    np.testing.assert_allclose(dists[-1], np.hypot(9.0, 9.0))


def test_3d_rgb_returns_per_channel():
    arr = np.zeros((10, 10, 3), dtype=float)
    arr[..., 0] = 1.0   # red plane = 1
    arr[..., 1] = 2.0   # green plane = 2
    arr[..., 2] = 3.0   # blue plane = 3
    p0 = np.array([0.0, 5.0])
    p1 = np.array([9.0, 5.0])
    _, values = compute_profile(arr, p0, p1)
    assert values.shape[0] == 3
    np.testing.assert_allclose(values[0], 1.0)
    np.testing.assert_allclose(values[1], 2.0)
    np.testing.assert_allclose(values[2], 3.0)


def test_zero_length_line_returns_at_least_two_points():
    arr = np.zeros((10, 10), dtype=float)
    p0 = np.array([4.0, 4.0])
    p1 = np.array([4.0, 4.0])
    dists, values = compute_profile(arr, p0, p1)
    assert len(dists) >= 2
    assert len(values) == len(dists)


def test_endpoints_outside_bounds_are_clipped():
    arr = np.arange(100, dtype=float).reshape(10, 10)
    # request a line that goes outside the array; sampling clamps
    p0 = np.array([-5.0, 5.0])
    p1 = np.array([15.0, 5.0])
    _, values = compute_profile(arr, p0, p1)
    # both ends should sample row 5
    np.testing.assert_allclose(values[0], arr[5, 0])
    np.testing.assert_allclose(values[-1], arr[5, -1])


def test_rgba_uses_first_three_channels():
    arr = np.zeros((10, 10, 4), dtype=float)
    arr[..., 0] = 1.0
    arr[..., 1] = 2.0
    arr[..., 2] = 3.0
    arr[..., 3] = 99.0   # alpha — must NOT appear
    p0 = np.array([0.0, 5.0])
    p1 = np.array([9.0, 5.0])
    _, values = compute_profile(arr, p0, p1)
    assert values.shape[0] == 3
    assert (values != 99.0).all()
