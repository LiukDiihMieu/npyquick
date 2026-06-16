# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import limits


@dataclass(frozen=True)
class ArrayStats:
    finite_min: float | None  # None when no finite values exist
    finite_max: float | None
    nan_count: int
    pos_inf_count: int
    neg_inf_count: int
    sampled: bool = False  # computed from a subsample of a large array

    @property
    def has_anomaly(self) -> bool:
        return self.nan_count > 0 or self.pos_inf_count > 0 or self.neg_inf_count > 0

    def anomaly_str(self) -> str:
        """Compact anomaly summary, e.g. 'NaN: 3  +Inf: 1'.

        For sampled stats, exact counts would be misleading (sparse anomalies
        may be missed or over-represented), so only a qualitative note is given.
        """
        if self.sampled:
            return "NaN/Inf present in sample" if self.has_anomaly else "no anomaly in sample"
        parts = []
        if self.nan_count:
            parts.append(f"NaN: {self.nan_count}")
        if self.pos_inf_count:
            parts.append(f"+Inf: {self.pos_inf_count}")
        if self.neg_inf_count:
            parts.append(f"-Inf: {self.neg_inf_count}")
        return "  ".join(parts)

    def range_str(self) -> str:
        """Return 'finite range [a, b]', plain 'range [a, b]', or 'no finite values'."""
        if self.finite_min is None:
            return "no finite values"
        prefix = "finite range" if self.has_anomaly else "range"
        approx = " (approx)" if self.sampled else ""
        return f"{prefix} [{self.finite_min:.4g}, {self.finite_max:.4g}]{approx}"


def is_real_numeric(array: np.ndarray) -> bool:
    """True for real integer and floating dtypes; False for complex and non-numeric."""
    return (
        np.issubdtype(array.dtype, np.number)
        and not np.issubdtype(array.dtype, np.complexfloating)
    )


def array_stats(array: np.ndarray) -> ArrayStats | None:
    """Compute finite range and anomaly counts for numeric arrays.

    Returns None for non-numeric, complex, or empty arrays.
    Integer arrays cannot contain NaN/Inf, so anomaly counts are always 0.
    Arrays whose element count exceeds HIST_MAX_SAMPLES are subsampled
    (range/counts become approximate, ``sampled=True``) to avoid materializing a
    full finite mask. This is a compute budget independent of the byte-based I/O
    threshold; downsample_stride returns 1 when within budget.
    """
    if not is_real_numeric(array) or array.size == 0:
        return None

    # ravel(order="K") flattens in memory order, so it stays a view for both C-
    # and F-contiguous arrays. A plain reshape(-1) is C-order and would copy a
    # whole Fortran-order memmap into RAM before sampling — defeating the large-
    # array protection. Order does not matter for min/max/anomaly counts.
    flat = array.ravel(order="K")
    stride = limits.downsample_stride(flat.size, limits.HIST_MAX_SAMPLES)
    sampled = stride > 1
    sample = np.asarray(flat[::stride]) if sampled else array

    if np.issubdtype(array.dtype, np.integer):
        lo, hi = float(sample.min()), float(sample.max())
        return ArrayStats(lo, hi, 0, 0, 0, sampled)

    nan_count = int(np.sum(np.isnan(sample)))
    pos_inf_count = int(np.sum(np.isposinf(sample)))
    neg_inf_count = int(np.sum(np.isneginf(sample)))
    finite = sample[np.isfinite(sample)]
    if finite.size == 0:
        return ArrayStats(None, None, nan_count, pos_inf_count, neg_inf_count, sampled)
    return ArrayStats(
        float(finite.min()), float(finite.max()),
        nan_count, pos_inf_count, neg_inf_count, sampled,
    )
