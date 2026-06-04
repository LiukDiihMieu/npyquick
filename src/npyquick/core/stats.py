from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ArrayStats:
    finite_min: float | None  # None when no finite values exist
    finite_max: float | None
    nan_count: int
    pos_inf_count: int
    neg_inf_count: int

    @property
    def has_anomaly(self) -> bool:
        return self.nan_count > 0 or self.pos_inf_count > 0 or self.neg_inf_count > 0

    def anomaly_str(self) -> str:
        """Return compact anomaly summary, e.g. 'NaN: 3  +Inf: 1'. Empty if none."""
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
        return f"{prefix} [{self.finite_min:.4g}, {self.finite_max:.4g}]"


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
    """
    if not is_real_numeric(array) or array.size == 0:
        return None
    if np.issubdtype(array.dtype, np.integer):
        lo, hi = float(array.min()), float(array.max())
        return ArrayStats(lo, hi, 0, 0, 0)
    nan_count = int(np.sum(np.isnan(array)))
    pos_inf_count = int(np.sum(np.isposinf(array)))
    neg_inf_count = int(np.sum(np.isneginf(array)))
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return ArrayStats(None, None, nan_count, pos_inf_count, neg_inf_count)
    return ArrayStats(
        float(finite.min()), float(finite.max()),
        nan_count, pos_inf_count, neg_inf_count,
    )
