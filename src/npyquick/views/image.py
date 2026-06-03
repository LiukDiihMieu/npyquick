from __future__ import annotations

import numpy as np
from scipy import ndimage
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter

from .base import BaseView


class ProfileCanvas(FigureCanvas):
    def __init__(self) -> None:
        fig = Figure(constrained_layout=True)
        self._ax = fig.add_subplot(111)
        super().__init__(fig)
        self._ax.set_xlabel("Distance (px)")
        self._ax.set_ylabel("Intensity")
        self._ax.set_title("Cross Section Profile")
        self._ax.grid(True, alpha=0.3)
        self._line = None

    def set_profile(self, distances: np.ndarray, values: np.ndarray) -> None:
        if self._line is None:
            (self._line,) = self._ax.plot(distances, values, color="steelblue", lw=1.5)
        else:
            self._line.set_xdata(distances)
            self._line.set_ydata(values)
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
        self._endpoints = np.zeros((2, 2), dtype=float)
        self._dragging: int | None = None
        self._cs_line = self._ep0 = self._ep1 = None
        self._pan_start: tuple | None = None

        self.mpl_connect("button_press_event", self._on_press)
        self.mpl_connect("motion_notify_event", self._on_motion)
        self.mpl_connect("button_release_event", self._on_release)
        self.mpl_connect("scroll_event", self._on_scroll)

    def load(self, data: np.ndarray) -> None:
        self._data = data.astype(float)
        h, w = data.shape
        self._fig.clear()
        self._ax = self._fig.add_subplot(111)
        im = self._ax.imshow(self._data, cmap="gray", origin="upper", interpolation="nearest")
        self._fig.colorbar(im, ax=self._ax, fraction=0.046, pad=0.04)
        self._endpoints = np.array([[w * 0.1, h * 0.5], [w * 0.9, h * 0.5]], dtype=float)
        self._cs_line = self._ep0 = self._ep1 = None
        self._init_artists()
        self._refresh_profile()
        self.draw()

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

    def _refresh_profile(self) -> None:
        if self._data is None:
            return
        p0, p1 = self._endpoints
        diff = p1 - p0
        n = max(2, int(np.hypot(*diff)) + 1)
        h, w = self._data.shape
        xs = np.clip(np.linspace(p0[0], p1[0], n), 0, w - 1)
        ys = np.clip(np.linspace(p0[1], p1[1], n), 0, h - 1)
        profile = ndimage.map_coordinates(self._data, [ys, xs], order=1)
        dists = np.linspace(0.0, float(np.hypot(*diff)), n)
        self._profile.set_profile(dists, profile)

    def _hit(self, xd: float, yd: float) -> int | None:
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
        if self._dragging is not None:
            if ev.inaxes is not self._ax:
                return
            h, w = self._data.shape
            x = float(np.clip(ev.xdata, 0, w - 1))
            y = float(np.clip(ev.ydata, 0, h - 1))
            self._endpoints[self._dragging] = [x, y]
            self._sync_artists()
            self._refresh_profile()
            self.draw_idle()
            self._on_status(f"Endpoint {self._dragging + 1}  x={x:.1f}  y={y:.1f}")
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

    def _on_release(self, ev) -> None:
        if ev.button == 1:
            self._dragging = None
            self._pan_start = None


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
        from PySide6.QtWidgets import QVBoxLayout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(sp)

    @classmethod
    def can_handle(cls, array: np.ndarray) -> bool:
        return array.ndim == 2 and np.issubdtype(array.dtype, np.number)

    def set_data(self, array: np.ndarray) -> None:
        self._canvas.load(array)
