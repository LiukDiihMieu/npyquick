from __future__ import annotations

import numpy as np
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import QLabel, QTableView, QVBoxLayout

from .base import BaseView


class NpyTableModel(QAbstractTableModel):
    MAX_ROWS = 10_000
    MAX_COLS = 10_000

    def __init__(self) -> None:
        super().__init__()
        self._array: np.ndarray | None = None
        self._flat = False

    def set_array(self, array: np.ndarray) -> None:
        self.beginResetModel()
        if array.ndim == 1:
            self._array = array
            self._flat = True
        elif array.ndim == 2:
            self._array = array
            self._flat = False
        else:
            # flatten leading dims for display: (d0*d1*..., last)
            self._array = array.reshape(-1, array.shape[-1])
            self._flat = False
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if self._array is None:
            return 0
        return min(len(self._array), self.MAX_ROWS)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if self._array is None:
            return 0
        if self._flat:
            return 1
        return min(self._array.shape[1], self.MAX_COLS)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or role != Qt.DisplayRole or self._array is None:
            return None
        r, c = index.row(), index.column()
        val = self._array[r] if self._flat else self._array[r, c]
        if isinstance(val, (np.floating, float)):
            return f"{val:.6g}"
        return str(val)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        return str(section)


class RawTableView(BaseView):
    VIEW_ID = "table"
    VIEW_NAME = "Table"

    def __init__(self) -> None:
        super().__init__()
        self._status = ""
        self._model = NpyTableModel()
        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.horizontalHeader().setDefaultSectionSize(90)
        self._info = QLabel()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._info)
        layout.addWidget(self._table)

    @classmethod
    def can_handle(cls, array: np.ndarray) -> bool:
        return True

    def set_data(self, array: np.ndarray) -> None:
        self._model.set_array(array)
        rows = self._model.rowCount()
        cols = self._model.columnCount()
        actual_rows = array.shape[0] if array.ndim >= 1 else 1
        clipped = rows < actual_rows
        self._status = f"shape {array.shape}  dtype {array.dtype}  —  showing {rows}×{cols}"
        if clipped:
            self._status += f"  (truncated from {actual_rows} rows)"
        self._info.setText(self._status)

    def idle_status(self) -> str:
        return self._status
