from __future__ import annotations

import os
import numpy as np
from scipy import ndimage
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, QSettings, QUrl
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSplitter, QStackedWidget, QVBoxLayout, QWidget,
)

from .base import BaseView


class DualProfileCanvas(FigureCanvas):
    def __init__(self) -> None:
        fig = Figure(constrained_layout=True)
        self._ax = fig.add_subplot(111)
        super().__init__(fig)
        self._setup_axes()
        self._lines: list = []
        self._n_profiles = 0

    def _setup_axes(self) -> None:
        self._ax.set_xlabel("Distance (px)")
        self._ax.set_ylabel("Intensity")
        self._ax.set_title("Cross Section Profile")
        self._ax.grid(True, alpha=0.3)

    def set_profiles(
        self,
        profile_data: list[tuple[np.ndarray, np.ndarray]],
        labels: list[str],
        colors: list[str],
    ) -> None:
        n = len(profile_data)
        if n != self._n_profiles:
            self._ax.cla()
            self._setup_axes()
            self._lines = []
            for (dists, vals), label, color in zip(profile_data, labels, colors):
                (line,) = self._ax.plot(dists, vals, color=color, lw=1.5, label=label)
                self._lines.append(line)
            if n > 1:
                self._ax.legend(loc="upper right", fontsize=8)
            self._n_profiles = n
        else:
            for line, (dists, vals) in zip(self._lines, profile_data):
                line.set_xdata(dists)
                line.set_ydata(vals)
        self._ax.relim()
        self._ax.autoscale_view()
        self.draw_idle()


class DualImageCanvas(FigureCanvas):
    _HIT_RADIUS = 12

    def __init__(
        self,
        label: str,
        on_status: callable,
        on_endpoints_changed: callable | None = None,
        on_drop: callable | None = None,
        editable: bool = True,
    ) -> None:
        self._fig = Figure(constrained_layout=True)
        super().__init__(self._fig)
        self._ax = self._fig.add_subplot(111)
        self._label = label
        self._on_status = on_status
        self._on_endpoints_changed = on_endpoints_changed
        self._on_drop = on_drop
        self._editable = editable
        self._data: np.ndarray | None = None
        self._endpoints = np.zeros((2, 2), dtype=float)
        self._dragging: int | None = None
        self._cs_line = self._ep0 = self._ep1 = None
        self._pan_start: tuple | None = None
        self._hover: tuple[int, int] | None = None
        self._im = None

        self.mpl_connect("button_press_event", self._on_press)
        self.mpl_connect("motion_notify_event", self._on_motion)
        self.mpl_connect("button_release_event", self._on_release)
        self.mpl_connect("scroll_event", self._on_scroll)
        self.mpl_connect("axes_leave_event", self._on_axes_leave)
        self.setAcceptDrops(on_drop is not None)

    def load(
        self,
        data: np.ndarray,
        cmap: str = "gray",
        vmin: float | None = None,
        vmax: float | None = None,
    ) -> None:
        self._data = data.astype(float)
        h, w = data.shape
        self._fig.clear()
        self._ax = self._fig.add_subplot(111)
        self._ax.set_title(self._label, fontsize=9)
        self._im = self._ax.imshow(
            self._data, cmap=cmap, vmin=vmin, vmax=vmax,
            origin="upper", interpolation="nearest",
        )
        self._fig.colorbar(self._im, ax=self._ax, fraction=0.046, pad=0.04)
        self._endpoints = np.array([[w * 0.1, h * 0.5], [w * 0.9, h * 0.5]], dtype=float)
        self._cs_line = self._ep0 = self._ep1 = None
        self._hover = None
        self._init_artists()
        self.draw()

    def get_endpoints(self) -> np.ndarray:
        return self._endpoints.copy()

    def set_endpoints(self, endpoints: np.ndarray) -> None:
        self._endpoints = endpoints.copy()
        if self._cs_line is not None:
            self._sync_artists()
            self.draw_idle()

    def set_clim(self, vmin: float | None, vmax: float | None) -> None:
        if self._im is not None:
            self._im.set_clim(vmin, vmax)
            self.draw_idle()

    def get_profile(self) -> tuple[np.ndarray, np.ndarray] | None:
        if self._data is None:
            return None
        p0, p1 = self._endpoints
        diff = p1 - p0
        n = max(2, int(np.hypot(*diff)) + 1)
        h, w = self._data.shape
        xs = np.clip(np.linspace(p0[0], p1[0], n), 0, w - 1)
        ys = np.clip(np.linspace(p0[1], p1[1], n), 0, h - 1)
        profile = ndimage.map_coordinates(self._data, [ys, xs], order=1)
        dists = np.linspace(0.0, float(np.hypot(*diff)), n)
        return dists, profile

    def status_str(self) -> str:
        parts = []
        if self._hover is not None and self._data is not None:
            x, y = self._hover
            parts.append(f"{self._label}  x={x}  y={y}  val={self._data[y, x]:.4g}")
        if self._data is not None:
            p0, p1 = self._endpoints
            parts.append(f"EP1({p0[0]:.0f}, {p0[1]:.0f}) → EP2({p1[0]:.0f}, {p1[1]:.0f})")
        return "  |  ".join(parts)

    # ------------------------------------------------------------------
    # Artists
    # ------------------------------------------------------------------

    def _init_artists(self) -> None:
        p0, p1 = self._endpoints
        (self._cs_line,) = self._ax.plot(
            [p0[0], p1[0]], [p0[1], p1[1]], color="yellow", lw=1.5, zorder=5
        )
        (self._ep0,) = self._ax.plot([p0[0]], [p0[1]], "o", color="cyan", ms=9, zorder=6)
        (self._ep1,) = self._ax.plot([p1[0]], [p1[1]], "o", color="magenta", ms=9, zorder=6)

    def _sync_artists(self) -> None:
        p0, p1 = self._endpoints
        self._cs_line.set_xdata([p0[0], p1[0]])
        self._cs_line.set_ydata([p0[1], p1[1]])
        self._ep0.set_xdata([p0[0]])
        self._ep0.set_ydata([p0[1]])
        self._ep1.set_xdata([p1[0]])
        self._ep1.set_ydata([p1[1]])

    # ------------------------------------------------------------------
    # Mouse interaction
    # ------------------------------------------------------------------

    def _hit(self, xd: float, yd: float) -> int | None:
        if not self._editable:
            return None
        click = self._ax.transData.transform([xd, yd])
        for i, ep in enumerate(self._endpoints):
            if np.hypot(*(click - self._ax.transData.transform(ep))) < self._HIT_RADIUS:
                return i
        return None

    def _reset_zoom(self) -> None:
        if self._data is None:
            return
        h, w = self._data.shape
        self._ax.set_xlim(-0.5, w - 0.5)
        self._ax.set_ylim(h - 0.5, -0.5)
        self.draw_idle()

    def _on_axes_leave(self, ev) -> None:
        self._hover = None
        self._on_status(self.status_str())

    def _on_scroll(self, ev) -> None:
        if ev.inaxes is not self._ax or self._data is None:
            return
        factor = 0.8 if ev.step > 0 else 1.25
        xc, yc = ev.xdata, ev.ydata
        xl = list(self._ax.get_xlim())
        yl = list(self._ax.get_ylim())
        xl = [xc + (xl[0] - xc) * factor, xc + (xl[1] - xc) * factor]
        yl = [yc + (yl[0] - yc) * factor, yc + (yl[1] - yc) * factor]
        h, w = self._data.shape
        xl[0] = max(xl[0], -0.5)
        xl[1] = min(xl[1], w - 0.5)
        yl[0] = min(yl[0], h - 0.5)
        yl[1] = max(yl[1], -0.5)
        if xl[0] >= xl[1] or yl[1] >= yl[0]:
            self._reset_zoom()
            return
        self._ax.set_xlim(xl)
        self._ax.set_ylim(yl)
        self.draw_idle()

    def _on_press(self, ev) -> None:
        if ev.inaxes is not self._ax or self._data is None:
            return
        if ev.button == 1:
            if ev.dblclick:
                self._reset_zoom()
            else:
                self._dragging = self._hit(ev.xdata, ev.ydata)
                if self._dragging is None:
                    self._pan_start = (
                        ev.x, ev.y,
                        list(self._ax.get_xlim()),
                        list(self._ax.get_ylim()),
                        self._ax.transData.inverted(),
                    )

    def _on_motion(self, ev) -> None:
        if self._data is None:
            return
        if ev.inaxes is self._ax:
            h, w = self._data.shape
            self._hover = (
                int(round(np.clip(ev.xdata, 0, w - 1))),
                int(round(np.clip(ev.ydata, 0, h - 1))),
            )
        else:
            self._hover = None

        if self._dragging is not None:
            if ev.inaxes is not self._ax:
                self._on_status(self.status_str())
                return
            h, w = self._data.shape
            x = float(np.clip(ev.xdata, 0, w - 1))
            y = float(np.clip(ev.ydata, 0, h - 1))
            self._endpoints[self._dragging] = [x, y]
            self._sync_artists()
            self.draw_idle()
            if self._on_endpoints_changed:
                self._on_endpoints_changed(self._endpoints)
        elif self._pan_start is not None:
            x0_px, y0_px, xlim0, ylim0, inv0 = self._pan_start
            p0 = inv0.transform([x0_px, y0_px])
            p1 = inv0.transform([ev.x, ev.y])
            dx, dy = p1[0] - p0[0], p1[1] - p0[1]
            h, w = self._data.shape
            xl = [xlim0[0] - dx, xlim0[1] - dx]
            yl = [ylim0[0] - dy, ylim0[1] - dy]
            span_x = xl[1] - xl[0]
            span_y = yl[0] - yl[1]
            if xl[0] < -0.5:
                xl = [-0.5, -0.5 + span_x]
            elif xl[1] > w - 0.5:
                xl = [w - 0.5 - span_x, w - 0.5]
            if yl[1] < -0.5:
                yl = [-0.5 + span_y, -0.5]
            elif yl[0] > h - 0.5:
                yl = [h - 0.5, h - 0.5 - span_y]
            self._ax.set_xlim(xl)
            self._ax.set_ylim(yl)
            self.draw_idle()

        self._on_status(self.status_str())

    def _on_release(self, ev) -> None:
        if ev.button == 1:
            self._dragging = None
            self._pan_start = None

    # ------------------------------------------------------------------
    # Drag and drop
    # ------------------------------------------------------------------

    def dragEnterEvent(self, ev) -> None:
        urls = ev.mimeData().urls()
        if urls and QUrl.toLocalFile(urls[0]).endswith(".npy"):
            ev.acceptProposedAction()

    def dropEvent(self, ev) -> None:
        path = QUrl.toLocalFile(ev.mimeData().urls()[0])
        if self._on_drop:
            self._on_drop(path)


class DualImageView(BaseView):
    VIEW_ID = "compare"
    VIEW_NAME = "Compare"
    ALWAYS_ENABLED = True

    def __init__(self, on_status: callable) -> None:
        super().__init__()
        self._on_status = on_status
        self._img1: np.ndarray | None = None
        self._img2: np.ndarray | None = None
        self._diff_mode: bool = False

        self._canvas1 = DualImageCanvas(
            "Img 1", on_status,
            on_endpoints_changed=self._on_img1_endpoints_changed,
            on_drop=lambda p: self._load_image(p, slot=1),
        )
        self._canvas2 = DualImageCanvas(
            "Img 2", on_status,
            on_endpoints_changed=self._on_img2_endpoints_changed,
            on_drop=lambda p: self._load_image(p, slot=2),
        )
        self._diff_canvas = DualImageCanvas(
            "Diff (Img1 − Img2)", on_status,
            editable=False,
        )
        self._profile = DualProfileCanvas()

        self._mid_stack = QStackedWidget()
        self._mid_stack.addWidget(self._canvas2)     # index 0
        self._mid_stack.addWidget(self._diff_canvas)  # index 1

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._canvas1)
        splitter.addWidget(self._mid_stack)
        splitter.addWidget(self._profile)
        splitter.setSizes([500, 500, 380])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_controls())
        layout.addWidget(splitter)

    # ------------------------------------------------------------------
    # Control bar
    # ------------------------------------------------------------------

    def _build_controls(self) -> QWidget:
        # Row 1: file open buttons + align + diff toggle
        self._open1_btn = QPushButton("Open Img 1")
        self._open1_btn.clicked.connect(lambda: self._open_dialog(1))
        self._img1_label = QLabel("—")
        self._img1_label.setMinimumWidth(140)

        self._open2_btn = QPushButton("Open Img 2")
        self._open2_btn.clicked.connect(lambda: self._open_dialog(2))
        self._img2_label = QLabel("—")
        self._img2_label.setMinimumWidth(140)

        self._align_btn = QPushButton("Align →")
        self._align_btn.setToolTip("Copy Img 1 endpoints to Img 2")
        self._align_btn.clicked.connect(self._align_endpoints)
        self._align_btn.setEnabled(False)

        self._diff_btn = QPushButton("Show Diff")
        self._diff_btn.setCheckable(True)
        self._diff_btn.clicked.connect(self._toggle_diff)
        self._diff_btn.setEnabled(False)

        row1 = QWidget()
        r1 = QHBoxLayout(row1)
        r1.setContentsMargins(6, 3, 6, 3)
        r1.addWidget(self._open1_btn)
        r1.addWidget(self._img1_label)
        r1.addSpacing(12)
        r1.addWidget(self._open2_btn)
        r1.addWidget(self._img2_label)
        r1.addStretch()
        r1.addWidget(self._align_btn)
        r1.addWidget(self._diff_btn)

        # Row 2: shared image clim + diff clim (hidden until diff mode)
        self._vmin_edit = QLineEdit()
        self._vmax_edit = QLineEdit()
        self._vmin_edit.setPlaceholderText("vmin")
        self._vmax_edit.setPlaceholderText("vmax")
        self._vmin_edit.setFixedWidth(80)
        self._vmax_edit.setFixedWidth(80)
        self._img_apply_btn = QPushButton("Apply")
        self._img_apply_btn.setFixedWidth(55)
        self._img_reset_btn = QPushButton("Reset")
        self._img_reset_btn.setFixedWidth(55)
        self._vmin_edit.returnPressed.connect(self._apply_img_clim)
        self._vmax_edit.returnPressed.connect(self._apply_img_clim)
        self._img_apply_btn.clicked.connect(self._apply_img_clim)
        self._img_reset_btn.clicked.connect(self._reset_img_clim)

        self._diff_vmin_edit = QLineEdit()
        self._diff_vmax_edit = QLineEdit()
        self._diff_vmin_edit.setPlaceholderText("vmin")
        self._diff_vmax_edit.setPlaceholderText("vmax")
        self._diff_vmin_edit.setFixedWidth(80)
        self._diff_vmax_edit.setFixedWidth(80)
        self._diff_apply_btn = QPushButton("Apply")
        self._diff_apply_btn.setFixedWidth(55)
        self._diff_reset_btn = QPushButton("Reset")
        self._diff_reset_btn.setFixedWidth(55)
        self._diff_vmin_edit.returnPressed.connect(self._apply_diff_clim)
        self._diff_vmax_edit.returnPressed.connect(self._apply_diff_clim)
        self._diff_apply_btn.clicked.connect(self._apply_diff_clim)
        self._diff_reset_btn.clicked.connect(self._reset_diff_clim)

        self._diff_clim_widget = QWidget()
        dcl = QHBoxLayout(self._diff_clim_widget)
        dcl.setContentsMargins(0, 0, 0, 0)
        dcl.addWidget(QLabel("  |  Diff range:  vmin:"))
        dcl.addWidget(self._diff_vmin_edit)
        dcl.addWidget(QLabel("vmax:"))
        dcl.addWidget(self._diff_vmax_edit)
        dcl.addWidget(self._diff_apply_btn)
        dcl.addWidget(self._diff_reset_btn)
        self._diff_clim_widget.setVisible(False)

        row2 = QWidget()
        r2 = QHBoxLayout(row2)
        r2.setContentsMargins(6, 3, 6, 3)
        r2.addWidget(QLabel("Image range:  vmin:"))
        r2.addWidget(self._vmin_edit)
        r2.addWidget(QLabel("vmax:"))
        r2.addWidget(self._vmax_edit)
        r2.addWidget(self._img_apply_btn)
        r2.addWidget(self._img_reset_btn)
        r2.addWidget(self._diff_clim_widget)
        r2.addStretch()

        ctrl = QWidget()
        cl = QVBoxLayout(ctrl)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(row1)
        cl.addWidget(row2)
        return ctrl

    # ------------------------------------------------------------------
    # File loading
    # ------------------------------------------------------------------

    def _open_dialog(self, slot: int) -> None:
        s = QSettings("npyquick", "npyquick")
        start = s.value("last_dir", os.path.expanduser("~"))
        path, _ = QFileDialog.getOpenFileName(
            self, f"Open Image {slot}", start, "NumPy files (*.npy)"
        )
        if path:
            s.setValue("last_dir", os.path.dirname(os.path.abspath(path)))
            self._load_image(path, slot)

    def _load_image(self, path: str, slot: int) -> None:
        try:
            data = np.load(path, allow_pickle=False)
        except Exception as exc:
            self._on_status(f"Error: {exc}")
            return
        if data.ndim != 2 or not np.issubdtype(data.dtype, np.number):
            self._on_status(
                f"Expected 2D grayscale array, got shape {data.shape} dtype {data.dtype}"
            )
            return
        other = self._img2 if slot == 1 else self._img1
        if other is not None and data.shape != other.shape:
            self._on_status(
                f"Shape mismatch: {data.shape} ≠ {other.shape} — both images must be the same size"
            )
            return

        if slot == 1:
            self._img1 = data
            self._img1_label.setText(os.path.basename(path))
        else:
            self._img2 = data
            self._img2_label.setText(os.path.basename(path))

        self._refresh_all()

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def _refresh_all(self) -> None:
        both = self._img1 is not None and self._img2 is not None
        vmin, vmax = self._compute_img_clim()

        if self._img1 is not None:
            self._canvas1.load(self._img1, vmin=vmin, vmax=vmax)
        if self._img2 is not None:
            self._canvas2.load(self._img2, vmin=vmin, vmax=vmax)

        self._align_btn.setEnabled(both)
        self._diff_btn.setEnabled(both)

        if both and self._diff_mode:
            self._refresh_diff()

        self._refresh_profile()

    def _compute_img_clim(self) -> tuple[float, float]:
        arrays = [a for a in (self._img1, self._img2) if a is not None]
        if not arrays:
            return 0.0, 1.0
        return float(min(a.min() for a in arrays)), float(max(a.max() for a in arrays))

    def _compute_diff_clim(self) -> tuple[float, float]:
        if self._img1 is None or self._img2 is None:
            return -1.0, 1.0
        diff = self._img1.astype(float) - self._img2.astype(float)
        absmax = max(abs(float(diff.min())), abs(float(diff.max())))
        return -absmax, absmax

    def _refresh_diff(self) -> None:
        if self._img1 is None or self._img2 is None:
            return
        diff = self._img1.astype(float) - self._img2.astype(float)
        vmin, vmax = self._compute_diff_clim()
        self._diff_canvas.load(diff, cmap="RdBu_r", vmin=vmin, vmax=vmax)
        self._diff_canvas.set_endpoints(self._canvas1.get_endpoints())

    def _refresh_profile(self) -> None:
        if self._diff_mode:
            if self._img1 is None or self._img2 is None:
                return
            result = self._diff_canvas.get_profile()
            if result is None:
                return
            self._profile.set_profiles([result], ["Diff"], ["crimson"])
        else:
            profile_data, labels, colors = [], [], []
            if self._img1 is not None:
                r = self._canvas1.get_profile()
                if r:
                    profile_data.append(r)
                    labels.append("Img 1")
                    colors.append("steelblue")
            if self._img2 is not None:
                r = self._canvas2.get_profile()
                if r:
                    profile_data.append(r)
                    labels.append("Img 2")
                    colors.append("darkorange")
            if profile_data:
                self._profile.set_profiles(profile_data, labels, colors)

    # ------------------------------------------------------------------
    # Callbacks & actions
    # ------------------------------------------------------------------

    def _on_img1_endpoints_changed(self, endpoints: np.ndarray) -> None:
        if self._diff_mode:
            self._diff_canvas.set_endpoints(endpoints)
        self._refresh_profile()

    def _on_img2_endpoints_changed(self, endpoints: np.ndarray) -> None:
        self._refresh_profile()

    def _align_endpoints(self) -> None:
        self._canvas2.set_endpoints(self._canvas1.get_endpoints())
        self._refresh_profile()

    def _toggle_diff(self, checked: bool) -> None:
        self._diff_mode = checked
        if checked:
            self._refresh_diff()
            self._mid_stack.setCurrentIndex(1)
            self._diff_clim_widget.setVisible(True)
            vmin, vmax = self._compute_diff_clim()
            self._diff_vmin_edit.setText(f"{vmin:.4g}")
            self._diff_vmax_edit.setText(f"{vmax:.4g}")
        else:
            self._mid_stack.setCurrentIndex(0)
            self._diff_clim_widget.setVisible(False)
        self._refresh_profile()

    # ------------------------------------------------------------------
    # Clim controls
    # ------------------------------------------------------------------

    def _apply_img_clim(self) -> None:
        try:
            vmin = float(self._vmin_edit.text()) if self._vmin_edit.text() else None
            vmax = float(self._vmax_edit.text()) if self._vmax_edit.text() else None
            self._canvas1.set_clim(vmin, vmax)
            self._canvas2.set_clim(vmin, vmax)
        except ValueError:
            pass

    def _reset_img_clim(self) -> None:
        self._vmin_edit.clear()
        self._vmax_edit.clear()
        vmin, vmax = self._compute_img_clim()
        self._canvas1.set_clim(vmin, vmax)
        self._canvas2.set_clim(vmin, vmax)

    def _apply_diff_clim(self) -> None:
        try:
            vmin = float(self._diff_vmin_edit.text()) if self._diff_vmin_edit.text() else None
            vmax = float(self._diff_vmax_edit.text()) if self._diff_vmax_edit.text() else None
            self._diff_canvas.set_clim(vmin, vmax)
        except ValueError:
            pass

    def _reset_diff_clim(self) -> None:
        vmin, vmax = self._compute_diff_clim()
        self._diff_vmin_edit.setText(f"{vmin:.4g}")
        self._diff_vmax_edit.setText(f"{vmax:.4g}")
        self._diff_canvas.set_clim(vmin, vmax)

    # ------------------------------------------------------------------
    # BaseView interface
    # ------------------------------------------------------------------

    @classmethod
    def can_handle(cls, array: np.ndarray) -> bool:
        return True

    def set_data(self, array: np.ndarray) -> None:
        pass

    def receive_external_file(self, array: np.ndarray, path: str) -> None:
        if array.ndim != 2 or not np.issubdtype(array.dtype, np.number):
            return
        self._img1 = array
        self._img2 = None
        self._img2_label.setText("—")
        self._align_btn.setEnabled(False)
        self._diff_btn.setEnabled(False)
        self._diff_btn.setChecked(False)
        self._diff_mode = False
        self._mid_stack.setCurrentIndex(0)
        self._diff_clim_widget.setVisible(False)
        self._img1_label.setText(os.path.basename(path))
        vmin, vmax = self._compute_img_clim()
        self._canvas1.load(self._img1, vmin=vmin, vmax=vmax)
        self._refresh_profile()

    def idle_status(self) -> str:
        return "Compare — open two .npy files of the same shape"
