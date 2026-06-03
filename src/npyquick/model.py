from __future__ import annotations

import numpy as np


class NpyDataModel:
    def __init__(self) -> None:
        self.array: np.ndarray | None = None
        self.path: str = ""
        self._arrays: dict[str, np.ndarray] = {}
        self._selected_key: str = ""

    def load(self, path: str) -> None:
        if path.endswith(".npz"):
            with np.load(path, allow_pickle=False) as f:
                self._arrays = {k: f[k] for k in f.files}
        else:
            self._arrays = {"": np.load(path, allow_pickle=False)}
        self.path = path
        self.select_array(next(iter(self._arrays)))

    def available_arrays(self) -> dict[str, np.ndarray]:
        return dict(self._arrays)

    def select_array(self, name: str) -> None:
        self.array = self._arrays[name]
        self._selected_key = name
