from __future__ import annotations

import os
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, QSettings, QUrl
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSplitter, QStackedWidget, QVBoxLayout, QWidget,
)

from ..core import limits
from ..core.coord import PixelTransform
from ..core.profile import compute_profile
from ..core.stats import array_stats
from ..model import NpyDataModel
from .base import BaseView, ColormappedView, ExportableMixin, SpatialView


def _fmt_unit(unit: str) -> str:
    return "" if unit == "None" else unit


class DualProfileCanvas(ExportableMixin, FigureCanvas):
    panel_name = "Profile"

    def __init__(self) -> None:
        fig = Figure(constrained_layout=True)
        self._ax = fig.add_subplot(111)
        super().__init__(fig)
        self._pixel_size: float = 1.0
        self._unit: str = "None"
        self._setup_axes()
        self._lines: list = []
        self._n_profiles = 0

    def _setup_axes(self) -> None:
        u = _fmt_unit(self._unit) if hasattr(self, "_unit") else ""
        label = f"Distance ({u})" if u else "Distance"
        self._ax.set_xlabel(label)
        self._ax.set_ylabel("Intensity")
        self._ax.set_title("Cross Section Profile")
        self._ax.grid(True, alpha=0.3)

    def set_pixel_size(self, ps: float, unit: str) -> None:
        self._pixel_size = ps
        self._unit = unit
        u = _fmt_unit(unit)
        self._ax.set_xlabel(f"Distance ({u})" if u else "Distance")
        self.draw_idle()

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
                (line,) = self._ax.plot(
                    dists * self._pixel_size, vals, color=color, lw=1.5, label=label
                )
                self._lines.append(line)
            if n > 1:
                self._ax.legend(loc="upper right", fontsize=8)
            self._n_profiles = n
        else:
            for line, (dists, vals) in zip(self._lines, profile_data):
                line.set_xdata(dists * self._pixel_size)
                line.set_ydata(vals)
        self._ax.relim()
        self._ax.autoscale_view()
        self.draw_idle()


class DualImageCanvas(ExportableMixin, FigureCanvas):
    _HIT_RADIUS = 12

    def __init__(
        self,
        label: str,
        on_status: callable,
        on_endpoints_changed: callable | None = None,
        on_drop: callable | None = None,
        editable: bool = True,
        accept_extensions: tuple[str, ...] = (".npy",),
    ) -> None:
        self._fig = Figure(constrained_layout=True)
        super().__init__(self._fig)
        self._ax = self._fig.add_subplot(111)
        self._label = label
        self.panel_name = label
        self._on_status = on_status
        self._on_endpoints_changed = on_endpoints_changed
        self._on_drop = on_drop
        self._editable = editable
        self._accept_extensions = accept_extensions
        self._data: np.ndarray | None = None       # full resolution (may be a memmap)
        self._disp: np.ndarray | None = None        # float display array (maybe downsampled)
        self._stride: int = 1                       # full-res pixels per display pixel
        self._endpoints = np.zeros((2, 2), dtype=float)
        self._dragging: int | None = None
        self._cs_line = self._ep0 = self._ep1 = None
        self._pan_start: tuple | None = None
        self._hover: tuple[int, int] | None = None
        self._im = None
        self._transform = PixelTransform()

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
        self._data = data
        h, w = data.shape
        # Downsample by spatial pixel count, before any astype, so a memmap is
        # never fully read into RAM. extent stays full-resolution so coordinates
        # and pixel-size labels remain correct; hover still reads full-res _data.
        s = limits.stride_for(h * w, limits.IMAGE_MAX_PIXELS)
        self._stride = s
        sub = data[::s, ::s] if s > 1 else data
        self._disp = np.asarray(sub, dtype=float)
        self._fig.clear()
        self._ax = self._fig.add_subplot(111)
        self._ax.set_title(self._label, fontsize=9)
        u = self._transform.format_unit()
        self._ax.set_xlabel(u)
        self._ax.set_ylabel(u)
        self._im = self._ax.imshow(
            self._disp, cmap=cmap, vmin=vmin, vmax=vmax,
            origin="upper", interpolation="nearest",
            extent=self._transform.extent(h, w),
        )
        self._fig.colorbar(self._im, ax=self._ax, fraction=0.046, pad=0.04)
        ps = self._transform.pixel_size
        self._endpoints = np.array(
            [[w * 0.1 * ps, h * 0.5 * ps], [w * 0.9 * ps, h * 0.5 * ps]], dtype=float
        )
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

    def get_view(self) -> tuple[tuple, tuple]:
        return self._ax.get_xlim(), self._ax.get_ylim()

    def set_view(self, xlim: tuple, ylim: tuple) -> None:
        self._ax.set_xlim(xlim)
        self._ax.set_ylim(ylim)
        self.draw_idle()

    def set_colormap(self, name: str) -> None:
        if self._im is not None:
            self._im.set_cmap(name)
            self.draw_idle()

    def get_profile(self) -> tuple[np.ndarray, np.ndarray] | None:
        if self._disp is None:
            return None
        # Sample the (float, possibly downsampled) display array: endpoint pixel
        # coords are full-resolution, so divide by the stride to reach the
        # display grid, then scale distances back to full-res pixel units.
        s = self._stride
        p0_px, p1_px = self._transform.to_pixel(self._endpoints)
        dists, values = compute_profile(self._disp, p0_px / s, p1_px / s)
        return dists * s, values

    def set_pixel_size(self, ps: float, unit: str) -> None:
        new_t = PixelTransform(ps, unit)
        if new_t == self._transform:
            return
        old_t = self._transform
        self._transform = new_t
        if self._data is None:
            return
        h, w = self._data.shape
        ratio = new_t.pixel_size / old_t.pixel_size
        self._endpoints *= ratio
        self._im.set_extent(new_t.extent(h, w))
        u = new_t.format_unit()
        self._ax.set_xlabel(u)
        self._ax.set_ylabel(u)
        self._reset_zoom()
        if self._cs_line is not None:
            self._sync_artists()
        self.draw_idle()

    def status_str(self) -> str:
        parts = []
        ps = self._transform.pixel_size
        u = self._transform.format_unit()
        if self._hover is not None and self._data is not None:
            x, y = self._hover
            xp, yp = x * ps, y * ps
            parts.append(f"{self._label}  x={xp:.4g}{u}  y={yp:.4g}{u}  val={self._data[y, x]:.4g}")
        if self._data is not None:
            p0, p1 = self._endpoints
            parts.append(f"EP1({p0[0]:.4g}, {p0[1]:.4g}) → EP2({p1[0]:.4g}, {p1[1]:.4g})")
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
        x0, x1, y0_bot, y1_top = self._transform.extent(h, w)
        self._ax.set_xlim(x0, x1)
        self._ax.set_ylim(y0_bot, y1_top)
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
        x_min, x_max, y_bot, y_top = self._transform.extent(h, w)
        xl[0] = max(xl[0], x_min)
        xl[1] = min(xl[1], x_max)
        yl[0] = min(yl[0], y_bot)
        yl[1] = max(yl[1], y_top)
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
        t = self._transform
        h, w = self._data.shape
        if ev.inaxes is self._ax:
            xp, yp = t.to_pixel([ev.xdata, ev.ydata])
            self._hover = (
                int(round(np.clip(xp, 0, w - 1))),
                int(round(np.clip(yp, 0, h - 1))),
            )
        else:
            self._hover = None

        if self._dragging is not None:
            if ev.inaxes is not self._ax:
                self._on_status(self.status_str())
                return
            x = t.clamp_x_physical(ev.xdata, w)
            y = t.clamp_y_physical(ev.ydata, h)
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
            x_min, x_max, y_bot, y_top = t.extent(h, w)
            xl = [xlim0[0] - dx, xlim0[1] - dx]
            yl = [ylim0[0] - dy, ylim0[1] - dy]
            span_x = xl[1] - xl[0]
            span_y = yl[0] - yl[1]
            if xl[0] < x_min:
                xl = [x_min, x_min + span_x]
            elif xl[1] > x_max:
                xl = [x_max - span_x, x_max]
            if yl[1] < y_top:
                yl = [y_top + span_y, y_top]
            elif yl[0] > y_bot:
                yl = [y_bot, y_bot - span_y]
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
        if urls and any(QUrl.toLocalFile(urls[0]).endswith(ext) for ext in self._accept_extensions):
            ev.acceptProposedAction()

    def dropEvent(self, ev) -> None:
        path = QUrl.toLocalFile(ev.mimeData().urls()[0])
        if self._on_drop:
            self._on_drop(path)


class DualImageView(BaseView, SpatialView, ColormappedView):
    VIEW_ID = "compare"
    VIEW_NAME = "Compare"
    ALWAYS_ENABLED = True

    def __init__(self) -> None:
        super().__init__()
        self._img1: np.ndarray | None = None
        self._img2: np.ndarray | None = None
        self._model2 = NpyDataModel()   # private second model: keeps Img 2 under
                                        # the same large-file guard as Img 1, while
                                        # main's single-shared-model structure stays intact
        self._diff_mode: bool = False
        self._colormap: str = "gray"
        self._on_img1_load: callable | None = None

        # Proxy so canvases always use the current callback even after set_on_status
        def _status_proxy(msg: str) -> None:
            self._on_status(msg)

        self._canvas1 = DualImageCanvas(
            "Img 1", _status_proxy,
            on_endpoints_changed=self._on_img1_endpoints_changed,
            on_drop=self._handle_img1_drop,
            accept_extensions=(".npy", ".npz"),
        )
        self._canvas2 = DualImageCanvas(
            "Img 2", _status_proxy,
            on_endpoints_changed=self._on_img2_endpoints_changed,
            on_drop=lambda p: self._load_img2(p),
            accept_extensions=(".npy",),
        )
        self._diff_canvas = DualImageCanvas(
            "Diff (Img1 − Img2)", _status_proxy,
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

    def set_img1_label(self, text: str) -> None:
        self._img1_label.setText(text)

    def set_on_img1_load(self, cb: callable) -> None:
        """Register callback invoked when Img 1 is opened via Compare controls.

        The callback receives the file path and is expected to call
        MainWindow.load_file(), which will push the array back via set_data().
        This keeps Img 1 in sync with the Image and Table views.
        """
        self._on_img1_load = cb

    def _open_dialog(self, slot: int) -> None:
        s = QSettings("npyquick", "npyquick")
        start = s.value("last_dir", os.path.expanduser("~"))
        if slot == 1:
            path, _ = QFileDialog.getOpenFileName(
                self, "Open Image 1", start, "NumPy files (*.npy *.npz);;All files (*)"
            )
            if path and self._on_img1_load is not None:
                self._on_img1_load(path)
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "Open Image 2", start, "NumPy files (*.npy);;All files (*)"
            )
            if path:
                s.setValue("last_dir", os.path.dirname(os.path.abspath(path)))
                self._load_img2(path)

    def _handle_img1_drop(self, path: str) -> None:
        if self._on_img1_load is not None:
            self._on_img1_load(path)

    def _load_img2(self, path: str) -> None:
        if path.endswith(".npz"):
            self._on_status("Img 2: use an .npy file (for .npz use File › Open to pick an array)")
            return
        try:
            self._model2.load(path)   # peek header + LARGE_BYTES guard + mmap + ceiling
        except Exception as exc:
            self._on_status(f"Error loading Img 2: {exc}")
            return
        data = self._model2.array
        if data.ndim != 2 or not np.issubdtype(data.dtype, np.number):
            self._on_status(
                f"Img 2: expected 2D numeric array, got shape {data.shape} dtype {data.dtype}"
            )
            return
        if self._img1 is not None and data.shape != self._img1.shape:
            self._on_status(
                f"Shape mismatch: {data.shape} ≠ {self._img1.shape} — both images must match"
            )
            return
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
            self._canvas1.load(self._img1, cmap=self._colormap, vmin=vmin, vmax=vmax)
        if self._img2 is not None:
            self._canvas2.load(self._img2, cmap=self._colormap, vmin=vmin, vmax=vmax)

        self._align_btn.setEnabled(both)
        self._diff_btn.setEnabled(both)

        if both and self._diff_mode:
            self._refresh_diff()

        self._refresh_profile()

    def _compute_img_clim(self) -> tuple[float, float]:
        arrays = [a for a in (self._img1, self._img2) if a is not None]
        if not arrays:
            return 0.0, 1.0
        mins, maxs = [], []
        for a in arrays:
            s = array_stats(a)
            if s is not None and s.finite_min is not None:
                mins.append(s.finite_min)
                maxs.append(s.finite_max)
        if not mins:
            return 0.0, 1.0
        return min(mins), max(maxs)

    def _compute_diff_clim(self) -> tuple[float, float]:
        if self._img1 is None or self._img2 is None:
            return -1.0, 1.0
        diff = self._img1.astype(float) - self._img2.astype(float)
        s = array_stats(diff)
        if s is None or s.finite_min is None:
            return -1.0, 1.0
        absmax = max(abs(s.finite_min), abs(s.finite_max))
        return -absmax, absmax

    def _refresh_diff(self) -> None:
        if self._img1 is None or self._img2 is None:
            return
        # Preserve zoom when re-entering diff mode; let the first load use the
        # full extent by only restoring when the canvas already had data.
        saved_view = (
            self._diff_canvas.get_view()
            if self._diff_canvas._data is not None
            else None
        )
        diff = self._img1.astype(float) - self._img2.astype(float)
        vmin, vmax = self._compute_diff_clim()
        self._diff_canvas.load(diff, cmap="RdBu_r", vmin=vmin, vmax=vmax)
        self._diff_canvas.set_endpoints(self._canvas1.get_endpoints())
        if saved_view is not None:
            self._diff_canvas.set_view(*saved_view)

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
        self._canvas2.set_view(*self._canvas1.get_view())
        self._diff_canvas.set_view(*self._canvas1.get_view())
        self._refresh_profile()

    def _toggle_diff(self, checked: bool) -> None:
        self._diff_mode = checked
        if checked:
            self._refresh_diff()
            self._diff_canvas.set_view(*self._canvas2.get_view())
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

    def set_data(self, array: np.ndarray, stats=None) -> None:
        if array.ndim != 2 or not np.issubdtype(array.dtype, np.number):
            return
        self._img1 = array
        self._img2 = None
        self._img1_label.setText("—")
        self._img2_label.setText("—")
        self._align_btn.setEnabled(False)
        self._diff_btn.setEnabled(False)
        self._diff_btn.setChecked(False)
        self._diff_mode = False
        self._mid_stack.setCurrentIndex(0)
        self._diff_clim_widget.setVisible(False)
        vmin, vmax = self._compute_img_clim()
        self._canvas1.load(self._img1, cmap=self._colormap, vmin=vmin, vmax=vmax)
        self._refresh_profile()

    def refresh_status(self) -> None:
        self._on_status("Compare — drag or open two 2D arrays of the same shape")

    def export_targets(self):
        targets = [
            ("Img 1", self._canvas1._export_figure),
            ("Img 2", self._canvas2._export_figure),
        ]
        if self._diff_mode:
            targets.append(("Diff", self._diff_canvas._export_figure))
        targets.append(("Profile", self._profile._export_figure))
        return targets

    def set_colormap(self, name: str) -> None:
        self._colormap = name
        self._canvas1.set_colormap(name)
        self._canvas2.set_colormap(name)

    def set_pixel_size(self, ps: float, unit: str) -> None:
        self._canvas1.set_pixel_size(ps, unit)
        self._canvas2.set_pixel_size(ps, unit)
        self._diff_canvas.set_pixel_size(ps, unit)
        self._profile.set_pixel_size(ps, unit)

