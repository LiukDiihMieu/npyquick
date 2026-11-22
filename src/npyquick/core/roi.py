# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

import numpy as np

from . import complexproj


class PixelRect(NamedTuple):
    """Original-array bounds, with exclusive right and bottom edges."""
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @classmethod
    def between(cls, start, end) -> PixelRect:
        x0, y0 = start
        x1, y1 = end
        return cls(min(x0, x1), min(y0, y1), max(x0, x1) + 1, max(y0, y1) + 1)


class RegionStats(NamedTuple):
    count: int
    mean: float | None
    std: float | None
    minimum: int | float | None
    maximum: int | float | None


# Bound temporary arrays even for extremely wide or non-contiguous memmaps.
BLOCK_VALUES = 128 * 1024


def region_stats(channel: np.ndarray, component: str | None = None,
                 cancelled: Callable[[], bool] = lambda: False) -> RegionStats:
    """Measure one channel exactly, using population or circular statistics."""
    count = 0
    minimum, maximum = np.inf, -np.inf
    mean = m2 = np.longdouble(0)
    cosine = sine = 0.0
    origin = 0
    blocks = np.nditer(channel, flags=["external_loop", "buffered", "zerosize_ok"],
                       op_flags=["readonly"], order="K", buffersize=BLOCK_VALUES)
    for block in blocks:
        if cancelled():
            raise InterruptedError
        valid = np.isfinite(block)
        if component == "Angle":
            valid &= block != 0  # A zero-magnitude value has no phase.
        values = block[valid]
        n = values.size
        if not n:
            continue
        if component:
            dtype = np.promote_types(values.dtype, np.complex128)
            values = complexproj.project(values.astype(dtype, copy=False), component)
        minimum = min(minimum, values.min().item())
        maximum = max(maximum, values.max().item())
        if component == "Angle":
            cosine += np.cos(values).sum(dtype=np.float64)
            sine += np.sin(values).sum(dtype=np.float64)
        else:
            values = values.astype(np.longdouble)
            if not count:
                origin = values[0]
            values -= origin
            # Merge block variances around their local means. Subtracting the
            # first value preserves small fluctuations on a large DC offset.
            local_mean = values.mean()
            values -= local_mean
            delta = local_mean - mean
            m2 += np.square(values).sum() + delta * delta * (count * n / (count + n))
            mean += delta * (n / (count + n))
        count += n
    if not count:
        return RegionStats(0, None, None, None, None)
    if component == "Angle":
        resultant = min(1.0, np.hypot(cosine, sine) / count)
        if resultant <= 8 * np.finfo(float).eps:
            mean, std = None, np.inf
        else:
            mean = np.arctan2(sine, cosine)
            std = np.sqrt(max(0.0, -2 * np.log(resultant)))
    else:
        mean += origin
        std = np.sqrt(m2 / count)
    return RegionStats(count, mean, std, minimum, maximum)
