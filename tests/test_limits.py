from __future__ import annotations

import numpy as np

from npyquick.core import limits


def test_array_nbytes_matches_numpy():
    assert limits.array_nbytes((3, 4), np.float32) == np.zeros((3, 4), np.float32).nbytes
    assert limits.array_nbytes((), np.int64) == 8
    assert limits.array_nbytes((10,), np.uint8) == 10


def test_is_large_threshold(monkeypatch):
    monkeypatch.setattr(limits, "LARGE_BYTES", 100)
    assert not limits.is_large(np.zeros(10, np.float32))     # 40 bytes
    assert limits.is_large(np.zeros(100, np.float32))        # 400 bytes


def test_stride_for_2d_keeps_within_budget():
    # 10_000 pixels, budget 100 -> stride ceil(sqrt(100)) = 10
    assert limits.stride_for(10_000, 100) == 10
    # already within budget
    assert limits.stride_for(50, 100) == 1


def test_downsample_stride_1d():
    assert limits.downsample_stride(1000, 100) == 10
    assert limits.downsample_stride(50, 100) == 1
    assert limits.downsample_stride(101, 100) == 2
