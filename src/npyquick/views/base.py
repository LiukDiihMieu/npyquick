from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import QWidget


class SpatialView:
    """Mixin: view supports physical pixel-size scaling."""
    def set_pixel_size(self, ps: float, unit: str) -> None:
        raise NotImplementedError


class ColormappedView:
    """Mixin: view supports matplotlib colormap selection."""
    def set_colormap(self, name: str) -> None:
        raise NotImplementedError


class BaseView(QWidget):
    VIEW_ID: str = ""
    VIEW_NAME: str = ""
    ALWAYS_ENABLED: bool = False

    @classmethod
    def can_handle(cls, array: np.ndarray) -> bool:
        raise NotImplementedError

    def set_data(self, array: np.ndarray) -> None:
        raise NotImplementedError

    def on_primary_load(self, array: np.ndarray, path: str) -> None:
        pass

    def idle_status(self) -> str:
        return ""
