from __future__ import annotations

import numpy as np
from scipy import ndimage
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from .base import BaseView


def _fmt_unit(unit: str) -> str:
    return "" if unit == "None" else unit


class ProfileCanvas(FigureCanvas):
    def __init__(self) -> None:
        fig = Figure(constrained_layout=True)
        self._ax = fig.add_subplot(111)
        super().__init__(fig)
        self._pixel_size: float = 1.0
        self._unit: str = "None"
        self._setup_axes()
        self._lines: list = []

    def _setup_axes(self) -> None:
        u = _fmt_unit(self._unit) if hasattr(self, "_unit") else "px"
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

    def set_profile(self, distances: np.ndarray, values: np.ndarray) -> None:
        # values: shape (N,) for grayscale, (C, N) for RGB
        is_rgb = values.ndim == 2
        n_ch = values.shape[0] if is_rgb else 1
        dists = distances * self._pixel_size

        if n_ch != len(self._lines):
            self._ax.cla()
            self._setup_axes()
            self._lines = []
            if is_rgb:
                colors = ["red", "green", "blue"]
                labels = ["R", "G", "B"]
                for i in range(n_ch):
                    (line,) = self._ax.plot(
                        dists, values[i], color=colors[i], lw=1.5, label=labels[i]
                    )
                    self._lines.append(line)
                self._ax.legend(loc="upper right", fontsize=8)
            else:
                (line,) = self._ax.plot(dists, values, color="steelblue", lw=1.5)
                self._lines.append(line)
        else:
            for i, line in enumerate(self._lines):
                line.set_xdata(dists)
                line.set_ydata(values[i] if is_rgb else values)

        self._ax.relim()
        self._ax.autoscale_view()
        self.draw_idle()


class ImageCanvas(FigureCanvas):
    _HIT_RADIUS = 12

    def __init__(self, profile: ProfileCanvas, on_status: callable) -> None:
        self._fig = Figure(constrained_layout=True)
        super().__init__(self._fig)
        self._ax = self._fig.add_subplot(111)
        self._profile = profile
        self._on_status = on_status
        self._data: np.ndarray | None = None
        self._rgb: bool = False
        self._endpoints = np.zeros((2, 2), dtype=float)
        self._dragging: int | None = None
        self._cs_line = self._ep0 = self._ep1 = None
        self._pan_start: tuple | None = None
        self._hover: tuple[int, int] | None = None
        self._im = None
        self._colormap: str = "gray"
        self._pixel_size: float = 1.0
        self._unit: str = "None"

        self.mpl_connect("button_press_event", self._on_press)
        self.mpl_connect("motion_notify_event", self._on_motion)
        self.mpl_connect("button_release_event", self._on_release)
        self.mpl_connect("scroll_event", self._on_scroll)
        self.mpl_connect("axes_leave_event", self._on_axes_leave)

    def _extent(self, h: int, w: int) -> list[float]:
        ps = self._pixel_size
        return [-0.5 * ps, (w - 0.5) * ps, (h - 0.5) * ps, -0.5 * ps]

    def load(self, data: np.ndarray) -> None:
        self._data = data
        self._rgb = data.ndim == 3
        self._fig.clear()
        self._ax = self._fig.add_subplot(111)

        if self._rgb:
            h, w = data.shape[:2]
            display = self._to_display_rgb(data)
            self._im = self._ax.imshow(
                display, origin="upper", interpolation="nearest",
                extent=self._extent(h, w),
            )
        else:
            h, w = data.shape
            self._im = self._ax.imshow(
                data.astype(float), cmap=self._colormap,
                origin="upper", interpolation="nearest",
                extent=self._extent(h, w),
            )
            self._fig.colorbar(self._im, ax=self._ax, fraction=0.046, pad=0.04)

        u = _fmt_unit(self._unit)
        self._ax.set_xlabel(u)
        self._ax.set_ylabel(u)
        self._endpoints = np.array(
            [[w * 0.1 * self._pixel_size, h * 0.5 * self._pixel_size],
             [w * 0.9 * self._pixel_size, h * 0.5 * self._pixel_size]],
            dtype=float,
        )
        self._cs_line = self._ep0 = self._ep1 = None
        self._hover = None
        self._init_artists()
        self._refresh_profile()
        self.draw()

    @staticmethod
    def _to_display_rgb(data: np.ndarray) -> np.ndarray:
        d = data[:, :, :3].astype(float)
        if np.issubdtype(data.dtype, np.integer):
            d = d / 255.0
        elif d.max() > 1.0:
            d = d / d.max()
        return np.clip(d, 0.0, 1.0)

    def status_str(self) -> str:
        parts = []
        ps = self._pixel_size
        u = _fmt_unit(self._unit)
        if self._hover is not None and self._data is not None:
            x, y = self._hover
            xp, yp = x * ps, y * ps
            coord = f"x={xp:.4g}{u}  y={yp:.4g}{u}"
            if self._rgb:
                v = self._data[y, x]
                ch = "RGBA"[: self._data.shape[2]]
                vals = "  ".join(f"{c}={v[i]:.4g}" for i, c in enumerate(ch))
                parts.append(f"{coord}  {vals}")
            else:
                parts.append(f"{coord}  val={self._data[y, x]:.4g}")
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
    # Profile computation
    # ------------------------------------------------------------------

    def _refresh_profile(self) -> None:
        if self._data is None:
            return
        ps = self._pixel_size
        p0, p1 = self._endpoints / ps   # back to pixel coords for sampling
        diff = p1 - p0
        n = max(2, int(np.hypot(*diff)) + 1)
        h, w = self._data.shape[:2]
        xs = np.clip(np.linspace(p0[0], p1[0], n), 0, w - 1)
        ys = np.clip(np.linspace(p0[1], p1[1], n), 0, h - 1)
        dists = np.linspace(0.0, float(np.hypot(*diff)), n)  # in pixels; ProfileCanvas scales

        if self._rgb:
            n_ch = min(self._data.shape[2], 3)
            values = np.stack([
                ndimage.map_coordinates(
                    self._data[:, :, c].astype(float), [ys, xs], order=1
                )
                for c in range(n_ch)
            ])
            self._profile.set_profile(dists, values)
        else:
            profile = ndimage.map_coordinates(self._data.astype(float), [ys, xs], order=1)
            self._profile.set_profile(dists, profile)

    # ------------------------------------------------------------------
    # Mouse interaction
    # ------------------------------------------------------------------

    def _hit(self, xd: float, yd: float) -> int | None:
        click = self._ax.transData.transform([xd, yd])
        for i, ep in enumerate(self._endpoints):
            if np.hypot(*(click - self._ax.transData.transform(ep))) < self._HIT_RADIUS:
                return i
        return None

    def _reset_zoom(self) -> None:
        if self._data is None:
            return
        ps = self._pixel_size
        h, w = self._data.shape[:2]
        self._ax.set_xlim(-0.5 * ps, (w - 0.5) * ps)
        self._ax.set_ylim((h - 0.5) * ps, -0.5 * ps)
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
        ps = self._pixel_size
        h, w = self._data.shape[:2]
        xl[0] = max(xl[0], -0.5 * ps)
        xl[1] = min(xl[1], (w - 0.5) * ps)
        yl[0] = min(yl[0], (h - 0.5) * ps)
        yl[1] = max(yl[1], -0.5 * ps)
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

        ps = self._pixel_size
        if ev.inaxes is self._ax:
            h, w = self._data.shape[:2]
            self._hover = (
                int(round(np.clip(ev.xdata / ps, 0, w - 1))),
                int(round(np.clip(ev.ydata / ps, 0, h - 1))),
            )
        else:
            self._hover = None

        if self._dragging is not None:
            if ev.inaxes is not self._ax:
                return
            h, w = self._data.shape[:2]
            x = float(np.clip(ev.xdata, -0.5 * ps, (w - 0.5) * ps))
            y = float(np.clip(ev.ydata, -0.5 * ps, (h - 0.5) * ps))
            self._endpoints[self._dragging] = [x, y]
            self._sync_artists()
            self._refresh_profile()
            self.draw_idle()
        elif self._pan_start is not None:
            x0_px, y0_px, xlim0, ylim0, inv0 = self._pan_start
            p0 = inv0.transform([x0_px, y0_px])
            p1 = inv0.transform([ev.x, ev.y])
            dx, dy = p1[0] - p0[0], p1[1] - p0[1]
            h, w = self._data.shape[:2]
            xl = [xlim0[0] - dx, xlim0[1] - dx]
            yl = [ylim0[0] - dy, ylim0[1] - dy]
            span_x = xl[1] - xl[0]
            span_y = yl[0] - yl[1]
            if xl[0] < -0.5 * ps:
                xl = [-0.5 * ps, -0.5 * ps + span_x]
            elif xl[1] > (w - 0.5) * ps:
                xl = [(w - 0.5) * ps - span_x, (w - 0.5) * ps]
            if yl[1] < -0.5 * ps:
                yl = [-0.5 * ps + span_y, -0.5 * ps]
            elif yl[0] > (h - 0.5) * ps:
                yl = [(h - 0.5) * ps, (h - 0.5) * ps - span_y]
            self._ax.set_xlim(xl)
            self._ax.set_ylim(yl)
            self.draw_idle()

        self._on_status(self.status_str())

    def _on_release(self, ev) -> None:
        if ev.button == 1:
            self._dragging = None
            self._pan_start = None

    def set_pixel_size(self, ps: float, unit: str) -> None:
        if self._data is None:
            self._pixel_size = ps
            self._unit = unit
            self._profile.set_pixel_size(ps, unit)
            return
        h, w = self._data.shape[:2]
        ratio = ps / self._pixel_size
        self._pixel_size = ps
        self._unit = unit
        self._endpoints *= ratio
        self._im.set_extent(self._extent(h, w))
        u = _fmt_unit(unit)
        self._ax.set_xlabel(u)
        self._ax.set_ylabel(u)
        self._profile.set_pixel_size(ps, unit)
        self._reset_zoom()
        self._sync_artists()
        self._refresh_profile()
        self.draw_idle()

    def set_colormap(self, name: str) -> None:
        self._colormap = name
        if self._im is not None and not self._rgb:
            self._im.set_cmap(name)
            self.draw_idle()

    def set_clim(self, vmin: float | None, vmax: float | None) -> None:
        if self._im is not None and not self._rgb:
            self._im.set_clim(vmin, vmax)
            self.draw_idle()

    def reset_clim(self) -> None:
        if self._im is not None and not self._rgb and self._data is not None:
            d = self._data.astype(float)
            self._im.set_clim(d.min(), d.max())
            self.draw_idle()


class ImageView(BaseView):
    VIEW_ID = "image"
    VIEW_NAME = "Image"

    def __init__(self, on_status: callable) -> None:
        super().__init__()
        self._profile = ProfileCanvas()
        self._canvas = ImageCanvas(self._profile, on_status)

        sp = QSplitter(Qt.Horizontal)
        sp.addWidget(self._canvas)
        sp.addWidget(self._profile)
        sp.setSizes([780, 480])

        self._vmin_edit = QLineEdit()
        self._vmax_edit = QLineEdit()
        self._vmin_edit.setPlaceholderText("vmin")
        self._vmax_edit.setPlaceholderText("vmax")
        self._vmin_edit.setFixedWidth(90)
        self._vmax_edit.setFixedWidth(90)
        self._apply_btn = QPushButton("Apply")
        self._apply_btn.setFixedWidth(60)
        self._reset_btn = QPushButton("Reset")
        self._reset_btn.setFixedWidth(60)
        self._vmin_edit.returnPressed.connect(self._apply_clim)
        self._vmax_edit.returnPressed.connect(self._apply_clim)
        self._apply_btn.clicked.connect(self._apply_clim)
        self._reset_btn.clicked.connect(self._reset_clim)

        ctrl = QWidget()
        ctrl_layout = QHBoxLayout(ctrl)
        ctrl_layout.setContentsMargins(6, 2, 6, 2)
        ctrl_layout.addWidget(QLabel("vmin:"))
        ctrl_layout.addWidget(self._vmin_edit)
        ctrl_layout.addWidget(QLabel("vmax:"))
        ctrl_layout.addWidget(self._vmax_edit)
        ctrl_layout.addWidget(self._apply_btn)
        ctrl_layout.addWidget(self._reset_btn)
        ctrl_layout.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(ctrl)
        layout.addWidget(sp)

    @classmethod
    def can_handle(cls, array: np.ndarray) -> bool:
        if array.ndim == 2:
            return np.issubdtype(array.dtype, np.number)
        if array.ndim == 3 and array.shape[2] == 3:
            return np.issubdtype(array.dtype, np.number)
        return False

    def set_data(self, array: np.ndarray) -> None:
        self._canvas.load(array)
        self._vmin_edit.clear()
        self._vmax_edit.clear()
        rgb = array.ndim == 3
        for w in (self._vmin_edit, self._vmax_edit, self._apply_btn, self._reset_btn):
            w.setEnabled(not rgb)

    def set_pixel_size(self, ps: float, unit: str) -> None:
        self._canvas.set_pixel_size(ps, unit)

    def set_colormap(self, name: str) -> None:
        self._canvas.set_colormap(name)

    def _apply_clim(self) -> None:
        try:
            vmin = float(self._vmin_edit.text()) if self._vmin_edit.text() else None
            vmax = float(self._vmax_edit.text()) if self._vmax_edit.text() else None
            self._canvas.set_clim(vmin, vmax)
        except ValueError:
            pass

    def _reset_clim(self) -> None:
        self._vmin_edit.clear()
        self._vmax_edit.clear()
        self._canvas.reset_clim()

    def idle_status(self) -> str:
        return self._canvas.status_str()
