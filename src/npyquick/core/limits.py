from __future__ import annotations

from math import ceil

import numpy as np

# Single definition of "large", based on the in-memory byte size of an array.
LARGE_BYTES = 512 * 1024**2          # 512 MiB

# npz members cannot be memory-mapped, so a selected member must fully
# materialize into RAM; refuse anything above this hard ceiling.
NPZ_MEMBER_CEILING = 2 * 1024**3     # 2 GiB

# Rendering budgets (these are downsampling/sampling targets, NOT the
# definition of "large"). 2048x2048 (~4.2M) stays below IMAGE_MAX_PIXELS.
IMAGE_MAX_PIXELS = 5_000_000
HIST_MAX_SAMPLES = 5_000_000
TABLE_MAX_PER_AXIS = 2_000


def array_nbytes(shape, dtype) -> int:
    """Bytes an array of this shape/dtype would occupy, from header metadata."""
    count = int(np.prod(shape, dtype=np.int64))
    return count * np.dtype(dtype).itemsize


def is_large(array: np.ndarray) -> bool:
    """True when the array exceeds the unified large-file threshold."""
    return array.nbytes > LARGE_BYTES


def stride_for(n_total: int, budget: int) -> int:
    """Per-axis stride for 2D downsampling so kept pixels stay near budget."""
    return max(1, ceil((n_total / budget) ** 0.5))


def downsample_stride(n_total: int, budget: int) -> int:
    """Stride for 1D (flattened) sampling so kept samples stay within budget."""
    return max(1, ceil(n_total / budget))
