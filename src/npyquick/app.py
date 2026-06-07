# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 LiukDiihMieu

from __future__ import annotations

import os

import numpy as np
from PySide6.QtCore import Qt, QSettings, QUrl
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QStatusBar,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from .core.stats import ArrayStats, array_stats
from .model import NpyDataModel


def _format_array_summary(array: np.ndarray, stats: ArrayStats | None = None) -> str:
    parts = [f"shape {array.shape}", f"dtype {array.dtype}"]
    if array.size == 0:
        parts.append("empty")
    else:
        if stats is None:
            stats = array_stats(array)
        if stats is not None:
            parts.append(stats.range_str())
            if stats.has_anomaly:
                parts.append(stats.anomaly_str())
    return "  |  ".join(parts)
from .views.base import ColormappedView, ExportableMixin, SpatialView
from .views.dual_image import DualImageView
from .views.histogram import HistogramView
from .views.image import ImageView
from .views.lineplot import LineplotView
from .views.pixel_size_dialog import PixelSizeDialog
from .views.table import RawTableView


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("npyquick")
        self.resize(1300, 700)
        self.setAcceptDrops(True)

        _s = QSettings("npyquick", "npyquick")
        saved = _s.value("last_dir", os.path.expanduser("~"))
        self._last_dir = saved if os.path.isdir(saved) else os.path.expanduser("~")
        self._colormap: str = _s.value("colormap", "gray")

        self._model = NpyDataModel()
        self._pixel_size: float = 1.0
        self._pixel_unit: str = "None"
        self._pixel_expr: str = "1"
        self._current_path: str = ""
        self._sb = QStatusBar()
        self.setStatusBar(self._sb)

        self._build_menu()
        self._build_central()

        copy_sc = QShortcut(QKeySequence.StandardKey.Copy, self)
        copy_sc.activated.connect(self._copy_focused_plot)
        save_sc = QShortcut(QKeySequence.StandardKey.Save, self)
        save_sc.activated.connect(self._export_focused_plot)

        next_tab_sc = QShortcut(QKeySequence("Ctrl+Tab"), self)
        next_tab_sc.activated.connect(self._next_tab)
        prev_tab_sc = QShortcut(QKeySequence("Ctrl+Shift+Tab"), self)
        prev_tab_sc.activated.connect(self._prev_tab)

        self._sb.showMessage("File › Open  (Ctrl+O)  to load a .npy or .npz file.")

        geom = _s.value("geometry")
        if geom:
            self.restoreGeometry(geom)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        fm = self.menuBar().addMenu("&File")
        self._file_menu = fm
        self._export_actions: list = []

        open_a = QAction("&Open…", self)
        open_a.setShortcut("Ctrl+O")
        open_a.triggered.connect(self.open_file)
        fm.addAction(open_a)

        reload_a = QAction("&Reload", self)
        reload_a.setShortcuts([QKeySequence("Ctrl+R"), QKeySequence("F5")])
        reload_a.triggered.connect(self._reload_file)
        reload_a.setEnabled(False)
        fm.addAction(reload_a)
        self._reload_action = reload_a

        fm.addSeparator()
        quit_a = QAction("&Quit", self)
        quit_a.setShortcut("Ctrl+Q")
        quit_a.triggered.connect(self.close)
        fm.addAction(quit_a)
        self._quit_action = quit_a

        fm.aboutToShow.connect(self._rebuild_export_menu)

        vm = self.menuBar().addMenu("&View")
        px_action = QAction("Set Pixel Size…", self)
        px_action.triggered.connect(self._open_pixel_size_dialog)
        vm.addAction(px_action)
        vm.addSeparator()
        cmap_menu = vm.addMenu("Colormap")
        colormaps = [
            ("gray", "Gray"),
            ("viridis", "Viridis"),
            ("plasma", "Plasma"),
            ("inferno", "Inferno"),
            ("magma", "Magma"),
            ("cividis", "Cividis"),
            ("hot", "Hot"),
            ("coolwarm", "Coolwarm"),
            ("RdBu_r", "RdBu (diverging)"),
            ("turbo", "Turbo"),
        ]
        group = QActionGroup(self)
        group.setExclusive(True)
        for name, label in colormaps:
            a = QAction(label, self, checkable=True)
            a.setChecked(name == self._colormap)
            a.triggered.connect(lambda checked, n=name: self._apply_colormap(n))
            group.addAction(a)
            cmap_menu.addAction(a)

    def _build_central(self) -> None:
        self._image_view = ImageView()
        self._lineplot_view = LineplotView()
        self._table_view = RawTableView()
        self._histogram_view = HistogramView()
        self._compare_view = DualImageView()

        self._views: list = [
            self._image_view, self._histogram_view,
            self._lineplot_view, self._table_view,
            self._compare_view,
        ]
        for v in self._views:
            v.set_on_status(self._sb.showMessage)
        self._image_view.set_on_clim_change(self._histogram_view.update_clim_marker)
        self._compare_view.set_on_img1_load(self.load_file)

        self._stack = QStackedWidget()
        for v in self._views:
            self._stack.addWidget(v)

        # Empty-state page — shown when no data is loaded or no npz member is
        # selected. Lives in the stack at an index that has no corresponding tab.
        self._empty_label = QLabel()
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setStyleSheet("color: #888; font-size: 16px;")
        self._empty_label.setWordWrap(True)
        self._empty_page = QWidget()
        _ep_layout = QVBoxLayout(self._empty_page)
        _ep_layout.addWidget(self._empty_label)
        self._stack.addWidget(self._empty_page)

        self._tabs = QTabBar()
        for v in self._views:
            self._tabs.addTab(v.VIEW_NAME)
        self._tabs.currentChanged.connect(self._on_tab_changed)

        self._array_combo = QComboBox()
        self._array_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._array_combo.setPlaceholderText("— select an array —")
        # activated fires on every user pick, even when re-selecting the same
        # index. currentIndexChanged would silently skip the first item if the
        # combo already rested on index 0 after npz population.
        self._array_combo.activated.connect(self._on_array_selected)
        self._array_bar = QWidget()
        bar_layout = QHBoxLayout(self._array_bar)
        bar_layout.setContentsMargins(6, 2, 6, 2)
        bar_layout.addWidget(QLabel("Array:"))
        bar_layout.addWidget(self._array_combo)
        bar_layout.addStretch()
        self._array_bar.setVisible(False)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._array_bar)
        layout.addWidget(self._tabs)
        layout.addWidget(self._stack)
        self.setCentralWidget(container)

        self._set_tabs_enabled([])
        self._show_empty(
            "Open a .npy or .npz file\n\n"
            "File › Open  (Ctrl+O)  or drag a file onto the window"
        )

    # ------------------------------------------------------------------
    # Tab state
    # ------------------------------------------------------------------

    def _show_empty(self, msg: str) -> None:
        self._empty_label.setText(msg)
        self._stack.setCurrentWidget(self._empty_page)
        has_always = any(v.ALWAYS_ENABLED for v in self._views)
        self._tabs.setVisible(has_always)

    def _on_tab_changed(self, index: int) -> None:
        if self._stack.currentWidget() is self._empty_page:
            if not self._views[index].ALWAYS_ENABLED:
                return
        self._stack.setCurrentIndex(index)
        self._views[index].refresh_status()

    def _set_tabs_enabled(self, compatible: list[str], preferred: str | None = None) -> None:
        for i, v in enumerate(self._views):
            self._tabs.setTabEnabled(i, v.ALWAYS_ENABLED or v.VIEW_ID in compatible)
        any_shown = bool(compatible) or any(v.ALWAYS_ENABLED for v in self._views)
        self._tabs.setVisible(any_shown)
        if not compatible:
            return
        target = preferred if preferred in compatible else None
        for i, v in enumerate(self._views):
            if v.VIEW_ID == target or (target is None and v.VIEW_ID in compatible):
                self._tabs.setCurrentIndex(i)
                self._stack.setCurrentIndex(i)
                break

    # ------------------------------------------------------------------
    # File loading
    # ------------------------------------------------------------------

    def open_file(self) -> None:
        start = self._last_dir if os.path.isdir(self._last_dir) else os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "Open NumPy File", start, "NumPy files (*.npy *.npz);;All files (*)"
        )
        if path:
            self.load_file(path)

    def load_file(self, path: str) -> bool:
        try:
            self._model.load(path)
        except Exception as exc:
            self._sb.showMessage(f"Error loading {path}: {exc}")
            return False

        self._current_path = path
        self._reload_action.setEnabled(True)
        self._last_dir = os.path.dirname(os.path.abspath(path))
        QSettings("npyquick", "npyquick").setValue("last_dir", self._last_dir)
        self.setWindowTitle(f"npyquick — {path}")

        metas = self._model.available_array_meta()

        if self._model.array is None:
            # .npz opened: no member selected yet — show picker and archive
            # summary; views remain disabled until the user selects an array.
            self._array_combo.blockSignals(True)
            self._array_combo.clear()
            for key, meta in metas.items():
                self._array_combo.addItem(
                    f"{key}   {list(meta.shape)}   {meta.dtype}", key
                )
            # Start with no item highlighted so that picking ANY entry — including
            # the first one — will fire the activated signal.
            self._array_combo.setCurrentIndex(-1)
            self._array_combo.blockSignals(False)
            self._array_bar.setVisible(True)
            self._set_tabs_enabled([])
            self._show_empty("Select an array from the dropdown above")
            n = len(metas)
            self._sb.showMessage(
                f"{os.path.basename(path)}  |  .npz  {n} array{'s' if n != 1 else ''}"
                "  — select one above to view"
            )
        else:
            # .npy: single array, no picker needed.
            self._array_bar.setVisible(False)
            self._refresh_views()
        return True

    def _refresh_views(self) -> None:
        array = self._model.array
        if array is None:
            return  # .npz with no member selected yet — nothing to display
        # Compute once and fan out to every view + the status summary, instead of
        # each consumer re-sampling and re-scanning the same array.
        stats = array_stats(array)
        compatible = [v.VIEW_ID for v in self._views if v.can_handle(array)]
        for v in self._views:
            if v.VIEW_ID in compatible:
                v.set_data(array, stats)
        if self._image_view.can_handle(array):
            self._histogram_view.update_clim_marker(*self._image_view.get_clim())
        else:
            self._histogram_view.update_clim_marker(None, None)
        self._compare_view.set_img1_label(os.path.basename(self._current_path))
        self._apply_pixel_size()
        self._apply_colormap(self._colormap)
        preferred = "lineplot" if self._lineplot_view.can_handle(array) else None
        self._set_tabs_enabled(compatible, preferred)
        self._sb.showMessage(
            f"{os.path.basename(self._current_path)}  |  {_format_array_summary(array, stats)}"
        )

    def _on_array_selected(self, index: int) -> None:
        key = self._array_combo.itemData(index)
        if key is None:
            return
        try:
            self._model.select_array(key)
        except Exception as exc:
            self._sb.showMessage(f"Cannot load array '{key}': {exc}")
            return
        self._refresh_views()

    def _reload_file(self) -> None:
        if self._current_path and self.load_file(self._current_path):
            self._sb.showMessage("File reloaded", 3000)

    def _next_tab(self) -> None:
        if not self._tabs.isVisible():
            return
        n = self._tabs.count()
        cur = self._tabs.currentIndex()
        for offset in range(1, n + 1):
            i = (cur + offset) % n
            if self._tabs.isTabEnabled(i):
                self._tabs.setCurrentIndex(i)
                break

    def _prev_tab(self) -> None:
        if not self._tabs.isVisible():
            return
        n = self._tabs.count()
        cur = self._tabs.currentIndex()
        for offset in range(1, n + 1):
            i = (cur - offset) % n
            if self._tabs.isTabEnabled(i):
                self._tabs.setCurrentIndex(i)
                break

    # ------------------------------------------------------------------
    # Pixel size
    # ------------------------------------------------------------------

    def _apply_pixel_size(self) -> None:
        for v in self._views:
            if isinstance(v, SpatialView):
                v.set_pixel_size(self._pixel_size, self._pixel_unit)

    def _apply_colormap(self, name: str) -> None:
        self._colormap = name
        QSettings("npyquick", "npyquick").setValue("colormap", name)
        for v in self._views:
            if isinstance(v, ColormappedView):
                v.set_colormap(name)

    def _open_pixel_size_dialog(self) -> None:
        dlg = PixelSizeDialog(self._pixel_expr, self._pixel_unit, parent=self)
        if dlg.exec():
            self._pixel_size = dlg.result_value
            self._pixel_unit = dlg.result_unit
            self._pixel_expr = dlg.result_expr
            self._apply_pixel_size()

    # ------------------------------------------------------------------
    # Drag and drop
    # ------------------------------------------------------------------

    def _has_data(self) -> bool:
        """Single source of truth for whether plots can be exported."""
        return self._model.array is not None

    def _rebuild_export_menu(self) -> None:
        for a in self._export_actions:
            self._file_menu.removeAction(a)
        self._export_actions.clear()

        sep = self._file_menu.insertSeparator(self._quit_action)
        self._export_actions.append(sep)

        targets = (
            self._views[self._tabs.currentIndex()].export_targets()
            if self._has_data() else []
        )

        if not targets:
            a = QAction("Export Plot", self)
            a.setEnabled(False)
            self._file_menu.insertAction(self._quit_action, a)
            self._export_actions.append(a)
        elif len(targets) == 1:
            _, fn = targets[0]
            a = QAction("Export Plot…", self)
            a.triggered.connect(fn)
            self._file_menu.insertAction(self._quit_action, a)
            self._export_actions.append(a)
        else:
            from PySide6.QtWidgets import QMenu
            sub = QMenu("Export Plot", self)
            for name, fn in targets:
                sub.addAction(f"{name}…").triggered.connect(fn)
            a = self._file_menu.insertMenu(self._quit_action, sub)
            self._export_actions.append(a)

    def _focused_canvas(self) -> ExportableMixin | None:
        w = QApplication.focusWidget()
        while w is not None:
            if isinstance(w, ExportableMixin):
                return w
            w = w.parentWidget()
        return None

    def _copy_focused_plot(self) -> None:
        """Ctrl+C copies the focused canvas; hints if nothing is exportable."""
        if not self._has_data():
            self._sb.showMessage("No plot loaded — open a file first", 2500)
            return
        canvas = self._focused_canvas()
        if canvas is None:
            self._sb.showMessage("Click a plot first, then press Ctrl+C to copy", 2500)
            return
        canvas._copy_to_clipboard()

    def _export_focused_plot(self) -> None:
        """Ctrl+S exports the focused canvas; hints if nothing is exportable."""
        if not self._has_data():
            self._sb.showMessage("No plot loaded — open a file first", 2500)
            return
        canvas = self._focused_canvas()
        if canvas is None:
            self._sb.showMessage("Click a plot first, then press Ctrl+S to export", 2500)
            return
        canvas._export_figure()

    def dragEnterEvent(self, ev) -> None:
        urls = ev.mimeData().urls()
        if urls and all(QUrl.toLocalFile(u).endswith((".npy", ".npz")) for u in urls):
            ev.acceptProposedAction()

    def dropEvent(self, ev) -> None:
        path = QUrl.toLocalFile(ev.mimeData().urls()[0])
        self.load_file(path)

    def closeEvent(self, ev) -> None:
        QSettings("npyquick", "npyquick").setValue("geometry", self.saveGeometry())
        super().closeEvent(ev)
