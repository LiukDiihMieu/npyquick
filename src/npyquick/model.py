# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import numpy as np

from .core import limits
from .core.npyheader import MemberMeta, peek_npy, peek_npz


class NpyDataModel:
    def __init__(self) -> None:
        self.array: np.ndarray | None = None
        self.path: str = ""
        self._is_npz = False
        self._metas: dict[str, MemberMeta] = {}
        self._selected_key: str = ""

    def load(self, path: str) -> None:
        if path.endswith(".npz"):
            metas = peek_npz(path)
            if not metas:
                raise ValueError("NPZ archive contains no arrays")
            # Deliberately do NOT materialize any member here: the first member
            # may be huge (or even over NPZ_MEMBER_CEILING). Caller discovers
            # available arrays via available_array_meta(), then calls
            # select_array() to materialize the chosen one.
            self._is_npz = True
            self._metas = metas
            self._selected_key = ""
            self.array = None
            self.path = path
            return

        meta = peek_npy(path)
        # Materialize up front so a bad file raises before we commit state.
        array = self._materialize(path, False, "", meta)

        self._is_npz = False
        self._metas = {"": meta}
        self._selected_key = ""
        self.array = array
        self.path = path

    def _materialize(
        self, path: str, is_npz: bool, key: str, meta: MemberMeta
    ) -> np.ndarray:
        if is_npz:
            if meta.nbytes > limits.NPZ_MEMBER_CEILING:
                raise ValueError(
                    f"Array '{key}' is {meta.nbytes / 1024**3:.1f} GiB, exceeding the "
                    f"{limits.NPZ_MEMBER_CEILING / 1024**3:.0f} GiB limit for .npz "
                    f"members (they cannot be memory-mapped)."
                )
            with np.load(path, allow_pickle=False) as f:
                return f[key]
        return self._load_npy(path, meta)

    @staticmethod
    def _load_npy(path: str, meta: MemberMeta) -> np.ndarray:
        # 0-d arrays are always tiny and pointless to map; everything else,
        # including structured dtypes, is memory-mappable and should be mapped
        # when large. (Structured arrays load fine here but only the table view
        # handles them — image/histogram/stats gate on is_real_numeric.)
        zero_d = meta.shape == ()
        if zero_d or meta.nbytes <= limits.LARGE_BYTES:
            return np.load(path, allow_pickle=False)
        # Large array: memory-map. Do NOT silently fall back to a full load on
        # failure — that would defeat the protection and risk OOM.
        try:
            return np.load(path, mmap_mode="r", allow_pickle=False)
        except (ValueError, OSError) as exc:
            raise RuntimeError(
                f"Array is {meta.nbytes / 1024**3:.1f} GiB and could not be "
                f"memory-mapped: {exc}"
            ) from exc

    @property
    def selected_key(self) -> str:
        """Key of the array currently materialized (empty if none/.npy)."""
        return self._selected_key

    def available_array_meta(self) -> dict[str, MemberMeta]:
        return dict(self._metas)

    def select_array(self, name: str) -> None:
        meta = self._metas[name]
        self.array = self._materialize(self.path, self._is_npz, name, meta)
        self._selected_key = name
