from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import QWidget


class BaseView(QWidget):
    VIEW_ID: str = ""
    VIEW_NAME: str = ""

    @classmethod
    def can_handle(cls, array: np.ndarray) -> bool:
        raise NotImplementedError

    def set_data(self, array: np.ndarray) -> None:
        raise NotImplementedError
