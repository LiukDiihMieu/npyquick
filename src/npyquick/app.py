from __future__ import annotations

import os

import numpy as np
from PySide6.QtCore import QSettings, QUrl
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QStackedWidget,
    QStatusBar,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from .model import NpyDataModel
from .views.dual_image import DualImageView
from .views.image import ImageView
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

        self._model = NpyDataModel()
        self._sb = QStatusBar()
        self.setStatusBar(self._sb)

        self._build_menu()
        self._build_central()
        self._sb.showMessage("File › Open  (Ctrl+O)  to load a .npy file.")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        fm = self.menuBar().addMenu("&File")
        open_a = QAction("&Open…", self)
        open_a.setShortcut("Ctrl+O")
        open_a.triggered.connect(self.open_file)
        fm.addAction(open_a)
        fm.addSeparator()
        quit_a = QAction("&Quit", self)
        quit_a.setShortcut("Ctrl+Q")
        quit_a.triggered.connect(self.close)
        fm.addAction(quit_a)

        vm = self.menuBar().addMenu("&View")
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
            a.setChecked(name == "gray")
            a.triggered.connect(lambda checked, n=name: self._image_view.set_colormap(n))
            group.addAction(a)
            cmap_menu.addAction(a)

    def _build_central(self) -> None:
        self._image_view = ImageView(self._sb.showMessage)
        self._table_view = RawTableView()
        self._compare_view = DualImageView(self._sb.showMessage)

        self._views: list = [self._image_view, self._table_view, self._compare_view]

        self._stack = QStackedWidget()
        for v in self._views:
            self._stack.addWidget(v)

        self._tabs = QTabBar()
        for v in self._views:
            self._tabs.addTab(v.VIEW_NAME)
        self._tabs.currentChanged.connect(self._on_tab_changed)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._tabs)
        layout.addWidget(self._stack)
        self.setCentralWidget(container)

        self._set_tabs_enabled([])
        # In main, Qt naturally ends on Table after startup (Image is disabled
        # first, Qt auto-switches to Table, then Table is also disabled with
        # nowhere else to go). In pcm, Compare is ALWAYS_ENABLED so Qt lands
        # there instead. Force Table as current to match main's startup state.
        table_index = next(i for i, v in enumerate(self._views) if v.VIEW_ID == "table")
        self._tabs.setCurrentIndex(table_index)
        self._stack.setCurrentIndex(table_index)

    # ------------------------------------------------------------------
    # Tab state
    # ------------------------------------------------------------------

    def _on_tab_changed(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        status = self._views[index].idle_status()
        if status:
            self._sb.showMessage(status)

    def _set_tabs_enabled(self, compatible: list[str]) -> None:
        for i, v in enumerate(self._views):
            enabled = getattr(v, "ALWAYS_ENABLED", False) or v.VIEW_ID in compatible
            self._tabs.setTabEnabled(i, enabled)
        # switch to first compatible tab — identical to main branch behaviour
        for i, v in enumerate(self._views):
            if v.VIEW_ID in compatible:
                self._tabs.setCurrentIndex(i)
                self._stack.setCurrentIndex(i)
                break

    # ------------------------------------------------------------------
    # File loading
    # ------------------------------------------------------------------

    def open_file(self) -> None:
        start = self._last_dir if os.path.isdir(self._last_dir) else os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "Open NPY File", start, "NumPy files (*.npy);;All files (*)"
        )
        if path:
            self.load_file(path)

    def load_file(self, path: str) -> None:
        try:
            self._model.load(path)
        except Exception as exc:
            self._sb.showMessage(f"Error loading {path}: {exc}")
            return

        array = self._model.array
        compatible = self._model.compatible_views()

        for v in self._views:
            if v.VIEW_ID in compatible:
                v.set_data(array)

        self._compare_view.receive_external_file(array, path)
        self._set_tabs_enabled(compatible)

        self._last_dir = os.path.dirname(os.path.abspath(path))
        QSettings("npyquick", "npyquick").setValue("last_dir", self._last_dir)
        self.setWindowTitle(f"npyquick — {path}")
        self._sb.showMessage(
            f"{os.path.basename(path)}  |  shape {array.shape}  |  {array.dtype}"
            + (f"  |  range [{array.min():.4g}, {array.max():.4g}]"
               if np.issubdtype(array.dtype, np.number) else "")
        )

    # ------------------------------------------------------------------
    # Drag and drop
    # ------------------------------------------------------------------

    def dragEnterEvent(self, ev) -> None:
        urls = ev.mimeData().urls()
        if urls and all(QUrl.toLocalFile(u).endswith(".npy") for u in urls):
            ev.acceptProposedAction()

    def dropEvent(self, ev) -> None:
        path = QUrl.toLocalFile(ev.mimeData().urls()[0])
        self.load_file(path)
