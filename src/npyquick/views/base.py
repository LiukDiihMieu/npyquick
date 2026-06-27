# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import io
from collections.abc import Callable
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import Qt, QFileInfo, QSettings
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QMainWindow, QMenu, QMessageBox, QWidget,
)

if TYPE_CHECKING:
    from ..core.stats import ArrayStats


class ExportableMixin:
    """Right-click + Ctrl+C / Ctrl+S export for any FigureCanvas subclass."""
    panel_name: str = "Figure"

    # Save-dialog name filters mapped to the extension Qt should append.
    _EXPORT_FILTERS = {"PNG (*.png)": "png", "SVG (*.svg)": "svg", "PDF (*.pdf)": "pdf"}

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # matplotlib canvases default to NoFocus; ClickFocus lets a click mark
        # this panel as the Ctrl+C / Ctrl+S target (resolved via focusWidget).
        self.setFocusPolicy(Qt.ClickFocus)
        self._on_selected: Callable = lambda _: None

    def set_on_selected(self, cb: Callable) -> None:
        """Register a callback invoked with this canvas when it is clicked."""
        self._on_selected = cb

    def _show_status(self, msg: str, timeout: int = 2000) -> None:
        win = self.window()
        if isinstance(win, QMainWindow):
            win.statusBar().showMessage(msg, timeout)

    def _exports_allowed(self) -> bool:
        # Duck-typed so the mixin stays decoupled from MainWindow (and works in
        # standalone tests where the parent has no _has_data method).
        check = getattr(self.window(), "_has_data", None)
        return bool(check()) if callable(check) else True

    def contextMenuEvent(self, ev) -> None:
        if not self._exports_allowed():
            return
        menu = QMenu(self)
        menu.addAction("Export this plot…", self.export_figure)
        menu.addAction("Copy to clipboard", self.copy_to_clipboard)
        menu.exec(ev.globalPos())

    def copy_to_clipboard(self) -> None:
        buf = io.BytesIO()
        try:
            self.figure.savefig(buf, format="png", dpi=300, bbox_inches="tight")
        except Exception as exc:
            # Rendering to an in-memory buffer rarely fails, but an unhandled
            # exception from this slot would otherwise vanish (or abort).
            QMessageBox.warning(self, "Copy failed", str(exc))
            return
        buf.seek(0)
        QApplication.clipboard().setImage(QImage.fromData(buf.getvalue()))
        self._show_status(f"{self.panel_name} copied to clipboard")

    def export_figure(self) -> None:
        s = QSettings("npyquick", "npyquick")
        start = s.value("last_export_dir") or s.value("last_dir", "")

        dlg = QFileDialog(self, f"Export {self.panel_name}")
        dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dlg.setNameFilters(list(self._EXPORT_FILTERS))
        if start:
            dlg.setDirectory(start)
        # Preselect the first filter and seed an extension-less name. We do NOT
        # use setDefaultSuffix to append the extension: it is re-synced via the
        # filterSelected signal, which does not fire in every environment (e.g.
        # the save dialog under Snap), leaving the suffix stale and saving the
        # wrong format (issue #33). selectedNameFilter() is reliable everywhere,
        # so we resolve the format and append the extension ourselves below.
        first_filter = next(iter(self._EXPORT_FILTERS))
        dlg.selectNameFilter(first_filter)
        dlg.selectFile(self.panel_name.replace(" ", "_"))

        if not dlg.exec():
            return
        path = dlg.selectedFiles()[0]
        # Resolve the format from the reliable selectedNameFilter(): honour a
        # recognized extension the user typed, otherwise take the chosen filter
        # (falling back to the default filter if the platform reports none), and
        # make the path carry it. format= is passed so the content always matches.
        typed = QFileInfo(path).suffix().lower()
        if typed in self._EXPORT_FILTERS.values():
            fmt = typed
        else:
            fmt = self._EXPORT_FILTERS.get(
                dlg.selectedNameFilter(), self._EXPORT_FILTERS[first_filter]
            )
            path = f"{path}.{fmt}"
        try:
            self.figure.savefig(path, format=fmt, dpi=300, bbox_inches="tight")
        except Exception as exc:
            # A full disk, missing permissions or an unwritable path would
            # otherwise fail silently (and could abort the process from this
            # Qt slot), leaving the user thinking the export succeeded.
            QMessageBox.critical(
                self, "Export failed",
                f"Could not save {QFileInfo(path).fileName()}:\n{exc}",
            )
            return
        s.setValue("last_export_dir", QFileInfo(path).absolutePath())
        self._show_status(f"{self.panel_name} saved to {QFileInfo(path).fileName()}", 3000)


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
        self._on_status: Callable = lambda _: None

    def set_on_status(self, cb: Callable) -> None:
        self._on_status = cb

    def set_on_canvas_selected(self, cb: Callable) -> None:
        pass

    def refresh_status(self) -> None:
        """Push the view's current status to the status bar. Called on tab switch."""

    @classmethod
    def can_handle(cls, array: np.ndarray) -> bool:
        raise NotImplementedError

    def set_data(self, array: np.ndarray, stats: ArrayStats | None = None) -> None:
        raise NotImplementedError

    def export_targets(self) -> list[tuple[str, Callable]]:
        """Return [(panel_name, export_fn), …] for File › Export Plot menu."""
        return []
