# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QSplitter,
    QVBoxLayout, QWidget,
)

from ..core import limits
from ..core.coord import PixelTransform
from ..core.profile import compute_profile
from ..core.stats import ArrayStats, array_stats, is_real_numeric
from .base import BaseView, ColormappedView, ExportableMixin, SpatialView


class ProfileCanvas(ExportableMixin, FigureCanvas):
    panel_name = "Profile"

    def __init__(self) -> None:
        fig = Figure(constrained_layout=True)
        self._ax = fig.add_subplot(111)
        super().__init__(fig)
        self._transform = PixelTransform()
        self._setup_axes()
        self._lines: list = []
        self.mpl_connect("button_press_event", self._on_press)

    def _setup_axes(self) -> None:
        u = self._transform.format_unit()
        label = f"Distance ({u})" if u else "Distance"
        self._ax.set_xlabel(label)
        self._ax.set_ylabel("Intensity")
        self._ax.set_title("Cross Section Profile")
        self._ax.grid(True, alpha=0.3)

    def set_pixel_size(self, ps: float, unit: str) -> None:
        new_t = PixelTransform(ps, unit)
        if new_t == self._transform:
            return
        self._transform = new_t
        u = new_t.format_unit()
        self._ax.set_xlabel(f"Distance ({u})" if u else "Distance")
        self.draw_idle()

    def set_profile(self, distances: np.ndarray, values: np.ndarray) -> None:
        # values: shape (N,) for grayscale, (C, N) for RGB
        is_rgb = values.ndim == 2
        n_ch = values.shape[0] if is_rgb else 1
        dists = distances * self._transform.pixel_size

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

    def _on_press(self, ev) -> None:
        self._on_selected(self)


class ImageCanvas(ExportableMixin, FigureCanvas):
    _HIT_RADIUS = 12
    panel_name = "Image"

    def __init__(self, profile: ProfileCanvas) -> None:
        self._fig = Figure(layout="compressed")
        super().__init__(self._fig)
        self._ax = self._fig.add_subplot(111)
        self._profile = profile
        self._on_status: Callable = lambda _: None
        self._data: np.ndarray | None = None      # full resolution (may be a memmap)
        self._disp: np.ndarray | None = None       # float display array (maybe downsampled)
        self._stride: int = 1                      # full-res pixels per display pixel
        self._rgb: bool = False
        self._endpoints = np.zeros((2, 2), dtype=float)
        self._dragging: int | None = None
        self._cs_line = self._ep0 = self._ep1 = None
        self._pan_start: tuple | None = None
        self._hover: tuple[int, int] | None = None
        self._im = None
        self._colormap: str = "gray"
        self._transform = PixelTransform()

        self.mpl_connect("button_press_event", self._on_press)
        self.mpl_connect("motion_notify_event", self._on_motion)
        self.mpl_connect("button_release_event", self._on_release)
        self.mpl_connect("scroll_event", self._on_scroll)
        self.mpl_connect("axes_leave_event", self._on_axes_leave)

    def set_on_status(self, cb: Callable) -> None:
        self._on_status = cb

    def load(self, data: np.ndarray) -> tuple[str | None, str | None]:
        self._data = data
        self._rgb = data.ndim == 3
        self._fig.clear()
        self._ax = self._fig.add_subplot(111)

        h, w = data.shape[:2]
        # Downsample by spatial pixel count, before any astype, so a memmap is
        # never fully read into RAM. This is a rendering budget independent of
        # the byte-based I/O threshold; stride_for returns 1 when within budget.
        # extent stays full-resolution so coordinates and pixel-size labels
        # remain correct.
        s = limits.stride_for(h * w, limits.IMAGE_MAX_PIXELS)
        self._stride = s
        downsample_str: str | None = None
        if s > 1:
            sub = data[::s, ::s]
            dh, dw = sub.shape[:2]
            downsample_str = f"downsampled {h}×{w} → {dh}×{dw}  (1/{s})"
        else:
            sub = data

        extent = self._transform.extent(h, w)
        norm_str: str | None = None
        if self._rgb:
            display, norm_str = self._prepare_rgb(sub)
            self._disp = display
            self._im = self._ax.imshow(
                display, origin="upper", interpolation="nearest", extent=extent,
            )
        else:
            # Keep the native dtype: imshow normalizes through clim, so a float64
            # copy here would only cost 2-8x memory for nothing. Profile sampling
            # reads this array with output=float to stay correct on integer data.
            self._disp = np.asarray(sub)
            self._im = self._ax.imshow(
                self._disp, cmap=self._colormap,
                origin="upper", interpolation="nearest", extent=extent,
            )
            self._fig.colorbar(self._im, ax=self._ax, fraction=0.046, pad=0.04)

        u = self._transform.format_unit()
        self._ax.set_xlabel(u)
        self._ax.set_ylabel(u)
        ps = self._transform.pixel_size
        self._endpoints = np.array(
            [[w * 0.1 * ps, h * 0.5 * ps], [w * 0.9 * ps, h * 0.5 * ps]],
            dtype=float,
        )
        self._cs_line = self._ep0 = self._ep1 = None
        self._hover = None
        self._init_artists()
        self._refresh_profile()
        self.draw()
        return norm_str, downsample_str

    @staticmethod
    def _prepare_rgb(data: np.ndarray) -> tuple[np.ndarray, str]:
        rgb = data[:, :, :3]
        if rgb.dtype == np.uint8:
            # imshow renders uint8 RGB in [0, 255] directly, so skip the float
            # copy entirely (the common case). Profile sampling then reports raw
            # 0-255 channel values, which is the natural scale for 8-bit color.
            return np.asarray(rgb), "uint8 [0, 255] — as-is"
        # Other dtypes need normalization for imshow; float32 halves the copy
        # cost versus float64 with no visible difference at display precision.
        d = rgb.astype(np.float32)
        if np.issubdtype(data.dtype, np.integer):
            maxval = np.iinfo(data.dtype).max
            d = d / maxval
            norm_str = f"{data.dtype} ÷ {maxval}"
        else:
            lo, hi = float(d.min()), float(d.max())
            if lo >= 0.0 and hi <= 1.0:
                norm_str = f"float [{lo:.3g}, {hi:.3g}] — as-is"
            else:
                span = hi - lo
                d = (d - lo) / span if span > 0 else np.zeros_like(d)
                norm_str = f"float [{lo:.3g}, {hi:.3g}] → [0, 1]  (global min-max)"
        return np.clip(d, 0.0, 1.0), norm_str

    def status_str(self) -> str:
        parts = []
        ps = self._transform.pixel_size
        u = self._transform.format_unit()
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
        if self._disp is None:
            return
        # Sample the (float, possibly downsampled) display array: endpoint pixel
        # coords are in full resolution, so divide by the stride to reach the
        # display grid, then scale distances back to full-res pixel units.
        s = self._stride
        p0_px, p1_px = self._transform.to_pixel(self._endpoints)
        dists, values = compute_profile(self._disp, p0_px / s, p1_px / s)
        self._profile.set_profile(dists * s, values)

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
        h, w = self._data.shape[:2]
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
        h, w = self._data.shape[:2]
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
        # Any click anywhere on this canvas selects it as the export target.
        self._on_selected(self)
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
        h, w = self._data.shape[:2]
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
                return
            x = t.clamp_x_physical(ev.xdata, w)
            y = t.clamp_y_physical(ev.ydata, h)
            self._endpoints[self._dragging] = [x, y]
            self._sync_artists()
            self._refresh_profile()
            self.draw_idle()
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

    def set_pixel_size(self, ps: float, unit: str) -> None:
        new_t = PixelTransform(ps, unit)
        if new_t == self._transform:
            return
        old_t = self._transform
        self._transform = new_t
        self._profile.set_pixel_size(ps, unit)
        if self._data is None:
            return
        h, w = self._data.shape[:2]
        ratio = new_t.pixel_size / old_t.pixel_size
        self._endpoints *= ratio
        self._im.set_extent(new_t.extent(h, w))
        u = new_t.format_unit()
        self._ax.set_xlabel(u)
        self._ax.set_ylabel(u)
        self._reset_zoom()
        self._sync_artists()
        self._refresh_profile()
        self.draw_idle()

    def set_colormap(self, name: str) -> None:
        if name == self._colormap:
            return
        self._colormap = name
        if self._im is not None and not self._rgb:
            self._im.set_cmap(name)
            self.draw_idle()

    def set_clim(self, vmin: float | None, vmax: float | None) -> None:
        if self._im is not None and not self._rgb:
            self._im.set_clim(vmin, vmax)
            self.draw_idle()

    def reset_clim(self) -> None:
        if self._im is None or self._rgb or self._data is None:
            return
        stats = array_stats(self._data)
        if stats is None or stats.finite_min is None:
            return  # all-NaN/Inf: nothing sensible to reset to
        self._im.set_clim(stats.finite_min, stats.finite_max)
        self.draw_idle()


class ImageView(BaseView, SpatialView, ColormappedView):
    VIEW_ID = "image"
    VIEW_NAME = "Image"

    def __init__(self) -> None:
        super().__init__()
        self._on_clim_change: Callable = lambda vmin, vmax: None
        self._profile = ProfileCanvas()
        self._canvas = ImageCanvas(self._profile)

        sp = QSplitter(Qt.Horizontal)
        sp.addWidget(self._canvas)
        sp.addWidget(self._profile)
        _saved = QSettings("npyquick", "npyquick").value("image_profile_splitter")
        sp.setSizes([int(x) for x in _saved] if _saved else [780, 480])
        sp.splitterMoved.connect(
            lambda pos, idx: QSettings("npyquick", "npyquick").setValue(
                "image_profile_splitter", sp.sizes()
            )
        )

        self._vmin_edit = QLineEdit()
        self._vmax_edit = QLineEdit()
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

        self._downsample_label = QLabel()
        self._downsample_label.setStyleSheet("color: #b8860b;")
        self._downsample_label.setVisible(False)
        self._norm_label = QLabel()
        self._norm_label.setVisible(False)
        self._anomaly_label = QLabel()
        self._anomaly_label.setStyleSheet("color: red;")
        self._anomaly_label.setVisible(False)

        ctrl = QWidget()
        # The control row is one line tall; never let it absorb vertical space.
        ctrl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        ctrl_layout = QHBoxLayout(ctrl)
        ctrl_layout.setContentsMargins(6, 3, 6, 3)
        ctrl_layout.addWidget(QLabel("vmin:"))
        ctrl_layout.addWidget(self._vmin_edit)
        ctrl_layout.addWidget(QLabel("vmax:"))
        ctrl_layout.addWidget(self._vmax_edit)
        ctrl_layout.addWidget(self._apply_btn)
        ctrl_layout.addWidget(self._reset_btn)
        ctrl_layout.addStretch()
        ctrl_layout.addWidget(self._downsample_label)
        ctrl_layout.addWidget(self._norm_label)
        ctrl_layout.addWidget(self._anomaly_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(ctrl)
        layout.addWidget(sp, 1)

    @classmethod
    def can_handle(cls, array: np.ndarray) -> bool:
        if array.size == 0:
            return False
        if array.ndim == 2:
            return is_real_numeric(array)
        if array.ndim == 3 and array.shape[2] == 3:
            return is_real_numeric(array)
        return False

    def set_data(self, array: np.ndarray, stats: ArrayStats | None = None) -> None:
        norm_str, downsample_str = self._canvas.load(array)
        if downsample_str is not None:
            self._downsample_label.setText(downsample_str)
            self._downsample_label.setVisible(True)
        else:
            self._downsample_label.setText("")
            self._downsample_label.setVisible(False)
        self._vmin_edit.clear()
        self._vmax_edit.clear()
        rgb = array.ndim == 3
        for w in (self._vmin_edit, self._vmax_edit, self._apply_btn, self._reset_btn):
            w.setEnabled(not rgb)
        if norm_str is not None:
            self._norm_label.setText(f"norm: {norm_str}")
            self._norm_label.setVisible(True)
        else:
            self._norm_label.setText("")
            self._norm_label.setVisible(False)
        if stats is None:
            stats = array_stats(array)
        if stats is not None and stats.has_anomaly:
            self._anomaly_label.setText(stats.anomaly_str())
            self._anomaly_label.setVisible(True)
        else:
            self._anomaly_label.setText("")
            self._anomaly_label.setVisible(False)

    def set_pixel_size(self, ps: float, unit: str) -> None:
        self._canvas.set_pixel_size(ps, unit)

    def set_colormap(self, name: str) -> None:
        self._canvas.set_colormap(name)

    def set_on_status(self, cb: Callable) -> None:
        super().set_on_status(cb)
        self._canvas.set_on_status(cb)

    def set_on_canvas_selected(self, cb: Callable) -> None:
        self._canvas.set_on_selected(cb)
        self._profile.set_on_selected(cb)

    def refresh_status(self) -> None:
        self._on_status(self._canvas.status_str())

    def export_targets(self):
        return [("Image", self._canvas.export_figure),
                ("Profile", self._profile.export_figure)]

    def set_on_clim_change(self, cb: Callable) -> None:
        self._on_clim_change = cb

    def get_clim(self) -> tuple[float | None, float | None]:
        if self._canvas._im is None or self._canvas._rgb:
            return None, None
        return self._canvas._im.get_clim()

    def _apply_clim(self) -> None:
        try:
            vmin = float(self._vmin_edit.text()) if self._vmin_edit.text() else None
            vmax = float(self._vmax_edit.text()) if self._vmax_edit.text() else None
            self._canvas.set_clim(vmin, vmax)
            self._on_clim_change(*self.get_clim())
        except ValueError:
            pass

    def _reset_clim(self) -> None:
        self._vmin_edit.clear()
        self._vmax_edit.clear()
        self._canvas.reset_clim()
        self._on_clim_change(*self.get_clim())

