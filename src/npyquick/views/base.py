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

    def __init__(self) -> None:
        super().__init__()
        self._on_status: callable = lambda _: None

    def set_on_status(self, cb: callable) -> None:
        self._on_status = cb

    def refresh_status(self) -> None:
        """Push the view's current status to the status bar. Called on tab switch."""

    @classmethod
    def can_handle(cls, array: np.ndarray) -> bool:
        raise NotImplementedError

    def set_data(self, array: np.ndarray) -> None:
        raise NotImplementedError
