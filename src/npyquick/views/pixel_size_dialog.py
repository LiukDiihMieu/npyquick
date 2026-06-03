from __future__ import annotations

import math

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

UNITS = ["px", "nm", "μm", "mm", "cm", "m", "km", "in", "ft", "yd", "mi", "None"]

_SETTINGS_KEY = "pixel_size_history"
_MAX_HISTORY = 5

_SAFE_NS = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}


def _eval_expr(text: str) -> float:
    text = text.strip()
    if not text:
        raise ValueError("empty expression")
    result = eval(text, {"__builtins__": {}}, _SAFE_NS)  # noqa: S307
    result = float(result)
    if result <= 0:
        raise ValueError("pixel size must be positive")
    return result


def _load_history() -> list[tuple[str, str]]:
    raw = QSettings("npyquick", "npyquick").value(_SETTINGS_KEY, [])
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            out.append((str(item[0]), str(item[1])))
    return out


def _save_history(expr: str, unit: str) -> None:
    history = _load_history()
    entry = (expr, unit)
    history = [h for h in history if h != entry]
    history.insert(0, entry)
    history = history[:_MAX_HISTORY]
    QSettings("npyquick", "npyquick").setValue(_SETTINGS_KEY, history)


class PixelSizeDialog(QDialog):
    def __init__(self, current_expr: str, current_unit: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Set Pixel Size")
        self.setMinimumWidth(340)

        self._expr_combo = QComboBox()
        self._expr_combo.setEditable(True)
        self._expr_combo.setInsertPolicy(QComboBox.NoInsert)
        self._expr_combo.lineEdit().setPlaceholderText("e.g.  3.45/10  or  0.5")

        self._unit_combo = QComboBox()
        self._unit_combo.addItems(UNITS)

        self._error_label = QLabel()
        self._error_label.setStyleSheet("color: red;")
        self._error_label.hide()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("Expression:", self._expr_combo)
        form.addRow("Unit:", self._unit_combo)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._error_label)
        layout.addWidget(buttons)

        self._populate(current_expr, current_unit)

        self.result_value: float = 1.0
        self.result_expr: str = current_expr
        self.result_unit: str = current_unit

    def _populate(self, current_expr: str, current_unit: str) -> None:
        history = _load_history()
        self._expr_combo.clear()
        exprs_seen: list[str] = []
        for expr, _ in history:
            if expr not in exprs_seen:
                self._expr_combo.addItem(expr)
                exprs_seen.append(expr)
        if current_expr and current_expr not in exprs_seen:
            self._expr_combo.insertItem(0, current_expr)
        self._expr_combo.setCurrentText(current_expr if current_expr else "1")

        idx = self._unit_combo.findText(current_unit)
        if idx >= 0:
            self._unit_combo.setCurrentIndex(idx)

    def _on_ok(self) -> None:
        expr = self._expr_combo.currentText().strip()
        try:
            value = _eval_expr(expr)
        except Exception as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
            return
        unit = self._unit_combo.currentText()
        _save_history(expr, unit)
        self.result_value = value
        self.result_expr = expr
        self.result_unit = unit
        self.accept()
