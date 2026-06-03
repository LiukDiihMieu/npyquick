from __future__ import annotations

import numpy as np
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import (
    QLabel, QSplitter, QStackedWidget, QTableView, QVBoxLayout, QWidget,
)

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


def _make_channel_widget(label: str, model: NpyTableModel) -> tuple[QWidget, QTableView]:
    table = QTableView()
    table.setModel(model)
    table.horizontalHeader().setDefaultSectionSize(70)
    lbl = QLabel(f"<b>{label}</b>")
    lbl.setAlignment(Qt.AlignCenter)
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.setContentsMargins(2, 2, 2, 2)
    layout.setSpacing(2)
    layout.addWidget(lbl)
    layout.addWidget(table)
    return w, table


class RawTableView(BaseView):
    VIEW_ID = "table"
    VIEW_NAME = "Table"

    def __init__(self) -> None:
        super().__init__()
        self._status = ""

        # single table (1D / 2D)
        self._single_model = NpyTableModel()
        self._single_table = QTableView()
        self._single_table.setModel(self._single_model)
        self._single_table.horizontalHeader().setDefaultSectionSize(90)

        # triple tables (RGB): R, G, B
        self._rgb_models = [NpyTableModel() for _ in range(3)]
        self._rgb_splitter = QSplitter(Qt.Horizontal)
        for name, model in zip("RGB", self._rgb_models):
            w, _ = _make_channel_widget(name, model)
            self._rgb_splitter.addWidget(w)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._single_table)   # index 0
        self._stack.addWidget(self._rgb_splitter)   # index 1

        self._info = QLabel()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._info)
        layout.addWidget(self._stack)

    @classmethod
    def can_handle(cls, array: np.ndarray) -> bool:
        return True

    def set_data(self, array: np.ndarray) -> None:
        if array.ndim == 3 and array.shape[2] == 3:
            for i, model in enumerate(self._rgb_models):
                model.set_array(array[:, :, i])
            self._stack.setCurrentIndex(1)
            rows = self._rgb_models[0].rowCount()
            cols = self._rgb_models[0].columnCount()
            h, w = array.shape[:2]
            truncated = rows < h or cols < w
            self._status = (
                f"shape {array.shape}  dtype {array.dtype}  —  "
                f"3 channels, each {rows}×{cols}"
                + ("  (truncated)" if truncated else "")
            )
        else:
            self._single_model.set_array(array)
            self._stack.setCurrentIndex(0)
            rows = self._single_model.rowCount()
            cols = self._single_model.columnCount()
            actual_rows = array.shape[0] if array.ndim >= 1 else 1
            self._status = f"shape {array.shape}  dtype {array.dtype}  —  showing {rows}×{cols}"
            if rows < actual_rows:
                self._status += f"  (truncated from {actual_rows} rows)"
        self._info.setText(self._status)

    def idle_status(self) -> str:
        return self._status
