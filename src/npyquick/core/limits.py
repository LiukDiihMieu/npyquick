# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from math import ceil

import numpy as np

# Single definition of "large", based on the in-memory byte size of an array.
LARGE_BYTES = 512 * 1024**2          # 512 MiB

# npz members cannot be memory-mapped, so a selected member must fully
# materialize into RAM; refuse anything above this hard ceiling.
NPZ_MEMBER_CEILING = 2 * 1024**3     # 2 GiB

# Rendering/compute budgets. These are independent of LARGE_BYTES: I/O cost
# scales with bytes (mmap / npz ceiling decisions use LARGE_BYTES), while
# rendering and statistics cost scales with element count. Both budgets are set
# to 4096^2, so realistic images (<=4096x4096, up to 384 MB RGB float64) render
# and are summarized at full resolution; only genuinely huge arrays downsample.
IMAGE_MAX_PIXELS = 16_777_216        # 4096 * 4096 spatial pixels (channels excluded)
HIST_MAX_SAMPLES = 16_777_216        # 4096 * 4096 flattened samples
LINEPLOT_MAX_POINTS = 1_000_000      # max display points for interactive line plot
TABLE_MAX_PER_AXIS = 2_000


def array_nbytes(shape, dtype) -> int:
    """Bytes an array of this shape/dtype would occupy, from header metadata."""
    count = int(np.prod(shape, dtype=np.int64))
    return count * np.dtype(dtype).itemsize


def stride_for(n_total: int, budget: int) -> int:
    """Per-axis stride for 2D downsampling so kept pixels stay near budget."""
    return max(1, ceil((n_total / budget) ** 0.5))


def downsample_stride(n_total: int, budget: int) -> int:
    """Stride for 1D (flattened) sampling so kept samples stay within budget."""
    return max(1, ceil(n_total / budget))


def sampled_flat_view(array: np.ndarray, budget: int) -> tuple[np.ndarray, int, int]:
    """Flatten and stride-sample an array within a compute budget.

    Returns ``(sample, n_total, n_used)``. downsample_stride returns 1 when the
    array is within budget, so the sample is then the full flat view and
    ``n_used == n_total``.

    ravel(order="K") flattens in memory order, so it stays a view for both C-
    and F-contiguous arrays. A plain reshape(-1) is C-order and would copy a
    whole Fortran-order memmap into RAM before sampling — defeating the large-
    array protection. Memory order is irrelevant to min/max, anomaly counts, and
    histogram binning, which is why every flat-sampling caller routes through
    here.
    """
    flat = array.ravel(order="K")
    n_total = flat.size
    stride = downsample_stride(n_total, budget)
    sample = np.asarray(flat[::stride])
    return sample, n_total, sample.size
