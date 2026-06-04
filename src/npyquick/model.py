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
                arrays = {k: f[k] for k in f.files}
            if not arrays:
                raise ValueError("NPZ archive contains no arrays")
        else:
            arrays = {"": np.load(path, allow_pickle=False)}

        # Commit to instance state only after full validation
        selected = next(iter(arrays))
        self._arrays = arrays
        self._selected_key = selected
        self.array = arrays[selected]
        self.path = path

    def available_arrays(self) -> dict[str, np.ndarray]:
        return dict(self._arrays)

    def select_array(self, name: str) -> None:
        self.array = self._arrays[name]
        self._selected_key = name
