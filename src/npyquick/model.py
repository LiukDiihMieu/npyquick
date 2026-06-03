from __future__ import annotations

import numpy as np


class NpyDataModel:
    def __init__(self) -> None:
        self.array: np.ndarray | None = None
        self.path: str = ""

    def load(self, path: str) -> None:
        self.array = np.load(path, allow_pickle=False)
        self.path = path

    def compatible_views(self) -> list[str]:
        if self.array is None:
            return []
        views = []
        a = self.array
        if a.ndim == 2 and np.issubdtype(a.dtype, np.number):
            views.append("image")
        views.append("table")
        return views
