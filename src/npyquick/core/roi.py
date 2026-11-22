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
    circular = component == "Angle"
    origin = 0
    blocks = np.nditer(channel, flags=["external_loop", "buffered", "zerosize_ok"],
                       op_flags=["readonly"], order="K", buffersize=BLOCK_VALUES)
    for block in blocks:
        if cancelled():
            raise InterruptedError
        valid = np.isfinite(block)
        if circular:
            valid &= block != 0  # A zero-magnitude value has no phase.
        values = block[valid]
        n = values.size
        if not n:
            continue
        if component:
            dtype = np.promote_types(values.dtype, np.complex128)
            values = complexproj.project(values.astype(dtype, copy=False), component)
        block_min = values.min()
        minimum = min(minimum, block_min.item())
        maximum = max(maximum, values.max().item())
        if values.dtype.kind in "iu" and values.itemsize == 8:
            # Keep 1-count differences even on platforms with a 64-bit long
            # double. Differences from the block minimum fit in a uint64.
            if not count:
                origin = block_min.item()
            offsets = values.astype(np.uint64, copy=False) - block_min.astype(np.uint64)
            values = offsets.astype(np.longdouble) + np.longdouble(block_min.item() - origin)
        else:
            values = np.exp(1j * values) if circular else values.astype(np.longdouble)
            if not count:
                origin = values[0]
            values -= origin
        # Merge block variances around their local means. A shared origin
        # preserves small fluctuations on a large DC offset.
        local_mean = values.mean()
        values -= local_mean
        delta = local_mean - mean
        m2 += (np.abs(values) ** 2).sum() + abs(delta) ** 2 * (count * n / (count + n))
        mean += delta * (n / (count + n))
        count += n
    if not count:
        return RegionStats(0, None, None, None, None)
    mean += origin
    variance = m2 / count
    if circular:
        resultant = abs(mean)
        if resultant <= 8 * np.finfo(float).eps:
            mean, std = None, np.inf
        else:
            mean = np.angle(mean)
            # On the unit circle, variance = 1 - resultant**2. Use the
            # variance directly when a tight phase cluster rounds resultant to 1.
            std = np.sqrt(-np.log1p(-variance) if variance < 0.5 else -2 * np.log(resultant))
    else:
        std = np.sqrt(variance)
    return RegionStats(count, mean, std, minimum, maximum)
