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
    complex_dtype: bool = False  # complex array: anomalies apply, range does not

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
        if self.complex_dtype:
            return ""  # a complex array has no single ordered min/max range
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

    Returns None for non-numeric or empty arrays. Complex arrays report anomaly
    counts (a value is anomalous when either part is NaN/Inf) but no range.
    Integer arrays cannot contain NaN/Inf, so anomaly counts are always 0.
    Arrays whose element count exceeds HIST_MAX_SAMPLES are subsampled
    (range/counts become approximate, ``sampled=True``) to avoid materializing a
    full finite mask. This is a compute budget independent of the byte-based I/O
    threshold; downsample_stride returns 1 when within budget.
    """
    if array.size == 0:
        return None
    is_complex = np.issubdtype(array.dtype, np.complexfloating)
    if not is_real_numeric(array) and not is_complex:
        return None

    sample, n_total, n_used = limits.sampled_flat_view(array, limits.HIST_MAX_SAMPLES)
    sampled = n_used < n_total

    if is_complex:
        # A complex value is anomalous when either part is non-finite. Classify
        # the Inf sign from whichever part is infinite (both-infinite is rare and
        # counts as +Inf). Range is undefined for complex, so it stays None.
        re, im = sample.real, sample.imag
        is_nan = np.isnan(sample)
        is_pinf = (np.isposinf(re) | np.isposinf(im)) & ~is_nan
        is_ninf = (np.isneginf(re) | np.isneginf(im)) & ~is_nan & ~is_pinf
        return ArrayStats(
            None, None, int(is_nan.sum()), int(is_pinf.sum()), int(is_ninf.sum()),
            sampled, complex_dtype=True,
        )

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
