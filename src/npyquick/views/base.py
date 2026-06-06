from __future__ import annotations

import io
import os
import re
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QMainWindow, QMenu, QWidget,
)

if TYPE_CHECKING:
    from ..core.stats import ArrayStats


class ExportableMixin:
    """Right-click + Ctrl+C clipboard export for any FigureCanvas subclass."""
    panel_name: str = "Figure"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # matplotlib canvases default to NoFocus; ClickFocus lets a click mark
        # this panel as the Ctrl+C copy target (resolved via focusWidget in app).
        self.setFocusPolicy(Qt.ClickFocus)

    def contextMenuEvent(self, ev) -> None:
        menu = QMenu(self)
        menu.addAction("Export this plot…", self._export_figure)
        menu.addAction("Copy to clipboard", self._copy_to_clipboard)
        menu.exec(ev.globalPos())

    def _copy_to_clipboard(self) -> None:
        buf = io.BytesIO()
        self.figure.savefig(buf, format="png", dpi=300, bbox_inches="tight")
        buf.seek(0)
        QApplication.clipboard().setImage(QImage.fromData(buf.getvalue()))
        win = self.window()
        if isinstance(win, QMainWindow):
            win.statusBar().showMessage(f"{self.panel_name} copied to clipboard", 2000)

    def _export_figure(self) -> None:
        s = QSettings("npyquick", "npyquick")
        start = s.value("last_export_dir") or s.value("last_dir", "")
        path, selected_filter = QFileDialog.getSaveFileName(
            self, f"Export {self.panel_name}", start,
            "PNG (*.png);;SVG (*.svg);;PDF (*.pdf)",
        )
        if not path:
            return
        # Qt does not auto-append the extension — extract it from the chosen filter.
        m = re.search(r'\*(\.\w+)', selected_filter)
        if m:
            ext = m.group(1).lower()
            if not path.lower().endswith(ext):
                path += ext
        s.setValue("last_export_dir", os.path.dirname(os.path.abspath(path)))
        self.figure.savefig(path, dpi=300, bbox_inches="tight")


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

    def set_data(self, array: np.ndarray, stats: ArrayStats | None = None) -> None:
        raise NotImplementedError

    def export_targets(self) -> list[tuple[str, callable]]:
        """Return [(panel_name, export_fn), …] for File › Export Plot menu."""
        return []
