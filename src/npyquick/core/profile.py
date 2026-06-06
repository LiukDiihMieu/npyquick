# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import numpy as np
from scipy import ndimage


def compute_profile(
    array: np.ndarray,
    p0_px: np.ndarray,
    p1_px: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Sample a cross-section profile along a line through an array.

    Args:
        array: 2D (H, W) or 3D (H, W, C) image.
        p0_px, p1_px: endpoint pixel coordinates, each shape (2,) as [x, y].

    Returns:
        (distances, values):
            distances: shape (N,), pixel distances from p0 to each sample.
            values: shape (N,) for 2D, shape (C, N) for 3D (C = min(array.shape[2], 3)).
    """
    p0 = np.asarray(p0_px, dtype=float)
    p1 = np.asarray(p1_px, dtype=float)
    diff = p1 - p0
    n = max(2, int(np.hypot(*diff)) + 1)
    h, w = array.shape[:2]
    xs = np.clip(np.linspace(p0[0], p1[0], n), 0, w - 1)
    ys = np.clip(np.linspace(p0[1], p1[1], n), 0, h - 1)
    dists = np.linspace(0.0, float(np.hypot(*diff)), n)

    # output=float makes map_coordinates interpolate integer inputs correctly
    # (otherwise an integer output dtype truncates each sample) without first
    # materializing a full float copy — the caller may pass a native-dtype
    # display array. order=1 needs no spline prefilter.
    if array.ndim == 3:
        n_ch = min(array.shape[2], 3)
        values = np.stack([
            ndimage.map_coordinates(array[:, :, c], [ys, xs], order=1, output=float)
            for c in range(n_ch)
        ])
    else:
        values = ndimage.map_coordinates(array, [ys, xs], order=1, output=float)

    return dists, values
