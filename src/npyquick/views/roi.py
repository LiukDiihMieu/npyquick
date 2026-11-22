# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from dataclasses import dataclass
from threading import Event

import numpy as np
from matplotlib.lines import Line2D
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtWidgets import QLabel

from ..core.coord import PixelTransform
from ..core.roi import BLOCK_VALUES, PixelRect, region_stats


@dataclass
class _Drag:
    start: tuple[int, int]
    screen_start: tuple[float, float]
    original: PixelRect | None
    handle: str
    moved: bool = False


class RectangleOverlay:
    """Pixel-aligned selection and its mouse gesture on one image canvas."""

    def __init__(self) -> None:
        self.bounds: PixelRect | None = None
        self.drag: _Drag | None = None
        self.artist: Line2D | None = None

    def attach(self, ax) -> None:
        self.artist = Line2D([], [], color="white", linestyle="--", gapcolor="#282828",
                             linewidth=1.2, marker="s", markersize=4,
                             markeredgecolor="#282828", zorder=7, visible=False)
        ax.add_artist(self.artist)  # An overlay must not change the data limits.

    def sync_artist(self, scale: float, *, active: bool) -> None:
        if self.artist is None:
            return
        self.artist.set_visible(active and self.bounds is not None)
        if active and self.bounds is not None:
            x0, y0, x1, y1 = (np.asarray(self.bounds) - 0.5) * scale
            self.artist.set_data((x0, x1, x1, x0, x0), (y0, y0, y1, y1, y0))

    def _handle(self, ev) -> str:
        if self.bounds is None:
            return "new"
        corners = self.artist.axes.transData.transform(self.artist.get_xydata()[:4])
        click = np.array([ev.x, ev.y])
        distances = np.linalg.norm(corners - click, axis=1)
        index = int(distances.argmin())
        inside = np.all((click >= corners.min(axis=0)) & (click <= corners.max(axis=0)))
        radius = 5 * self.artist.figure.dpi / 72
        if inside:  # Leave the center of even a very small box available to move.
            radius = min(radius, np.ptp(corners, axis=0).min() / 3)
        if distances[index] <= radius:
            return ("nw", "ne", "se", "sw")[index]
        return "move" if inside else "new"

    def cursor(self, ev):
        handle = self.drag.handle if self.drag else self._handle(ev)
        if handle == "move":
            return Qt.SizeAllCursor
        if handle in ("nw", "se"):
            return Qt.SizeFDiagCursor
        if handle in ("ne", "sw"):
            return Qt.SizeBDiagCursor
        return Qt.CrossCursor

    def _pixel(self, ev, transform: PixelTransform, shape) -> tuple[int, int]:
        # A release outside the axes still has screen coordinates.
        if ev.inaxes is self.artist.axes:
            xy = ev.xdata, ev.ydata
        else:
            xy = self.artist.axes.transData.inverted().transform((ev.x, ev.y))
        return transform.pixel_index(xy, shape)

    def press(self, ev, transform, shape) -> None:
        self.drag = _Drag(self._pixel(ev, transform, shape), (ev.x, ev.y),
                          self.bounds, self._handle(ev))

    def dragged_bounds(self, ev, transform, shape) -> PixelRect | None:
        drag = self.drag
        x, y = self._pixel(ev, transform, shape)
        dx, dy = x - drag.start[0], y - drag.start[1]
        sx, sy = drag.screen_start
        if dx or dy or abs(ev.x - sx) + abs(ev.y - sy) >= 3:
            drag.moved = True
        if not drag.moved:
            return self.bounds  # Clicking a complex panel only selects its component.
        box = drag.original
        if drag.handle == "new":
            return PixelRect.between(drag.start, (x, y))
        h, w = shape[:2]
        if drag.handle == "move":
            dx = min(max(dx, -box.left), w - box.right)
            dy = min(max(dy, -box.top), h - box.bottom)
            return PixelRect(box.left + dx, box.top + dy, box.right + dx, box.bottom + dy)
        x0, x1 = (box.left, box.right - 1) if "e" in drag.handle else (box.right - 1, box.left)
        y0, y1 = (box.top, box.bottom - 1) if "s" in drag.handle else (box.bottom - 1, box.top)
        return PixelRect.between((x0, y0), (min(max(x1 + dx, 0), w - 1),
                                            min(max(y1 + dy, 0), h - 1)))


def _format_stat(value: int | float | None) -> str:
    if value is None:
        return "—"
    return str(value) if isinstance(value, int) else f"{value:.5g}"


def _measure(region: np.ndarray, component: str | None, cancelled: Event) -> str:
    channels = zip("RGB", np.moveaxis(region, -1, 0)) if region.ndim == 3 else [(component, region)]
    parts = []
    for name, channel in channels:
        stats = region_stats(channel, component, cancelled.is_set)
        prefix = f"{name}  " if name else ""
        mean_label, std_label = ("Circular mean", "Circular std") if component == "Angle" else ("Mean", "Std")
        values = (f"{mean_label} {_format_stat(stats.mean)}   {std_label} {_format_stat(stats.std)}"
                  f"   Min {_format_stat(stats.minimum)}   Max {_format_stat(stats.maximum)}")
        if component == "Angle":
            values += "  (rad)"
        if stats.count < channel.size:
            values += f"   Valid {stats.count}/{channel.size}"
        parts.append(prefix + values)
    return "\n".join(parts)


class _Result(QObject):
    ready = Signal(object, str)


class _MeasureRegion(QRunnable):
    def __init__(self, region, component, cancelled):
        super().__init__()
        self.region = region
        self.component = component
        self.cancelled = cancelled
        self.result = _Result()

    def run(self) -> None:
        try:
            text = _measure(self.region, self.component, self.cancelled)
        except InterruptedError:
            return
        except (OSError, ValueError, MemoryError) as exc:
            text = f"Measurement failed ({exc})"
        self.result.ready.emit(self.cancelled, text)


class RoiReadout(QLabel):
    def __init__(self) -> None:
        super().__init__()
        self.setContentsMargins(7, 2, 7, 2)
        self.setTextFormat(Qt.PlainText)
        self.setWordWrap(True)
        self._transform = PixelTransform()
        self._bounds: PixelRect | None = None
        self._region: np.ndarray | None = None
        self._component: str | None = None
        self._cancelled: Event | None = None
        self._result = ""

    def set_scale(self, transform: PixelTransform) -> None:
        self._transform = transform
        self._update_text()

    def set_region(self, array: np.ndarray | None, bounds: PixelRect | None,
                   component: str | None, finished: bool) -> None:
        self._cancel()
        self._bounds = bounds
        self._region = None
        self._component = component
        self._result = ""
        if finished and bounds is not None:
            self._region = array[bounds.top:bounds.bottom, bounds.left:bounds.right]
            if self.isVisible():
                self._start()
        self._update_text()

    def _update_text(self) -> None:
        rect = self._bounds
        if rect is None:
            self.setText("Drag on the image to select a rectangle.")
            return
        text = f"ROI  {rect.width} × {rect.height} px"
        unit = self._transform.format_unit()
        if unit:
            ps = self._transform.pixel_size
            text += f"  ({rect.width * ps:.5g} × {rect.height * ps:.5g} {unit})"
        if self._result:
            line = text + "     " + self._result.replace("\n", "     |     ")
            if "\n" in self._result and self.fontMetrics().horizontalAdvance(line) > self.contentsRect().width():
                text += "\n" + self._result
            else:
                text = line
        elif self._region is not None:
            text += "     Measuring…"
        self.setText(text)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if event.size().width() != event.oldSize().width() and "\n" in self._result:
            self._update_text()

    def _cancel(self) -> None:
        if self._cancelled is not None:
            self._cancelled.set()
            self._cancelled = None

    def _start(self) -> None:
        cancel = Event()
        if self._region.size <= BLOCK_VALUES and not isinstance(self._region, np.memmap):
            self._result = _measure(self._region, self._component, cancel)
            return
        self._cancelled = cancel
        job = _MeasureRegion(self._region, self._component, cancel)
        job.result.ready.connect(self._receive, Qt.QueuedConnection)
        QThreadPool.globalInstance().start(job)

    @Slot(object, str)
    def _receive(self, cancel, result) -> None:
        if cancel is self._cancelled:
            self._cancelled = None
            self._result = result
            self._update_text()

    def hideEvent(self, event) -> None:
        self._cancel()
        super().hideEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._region is not None and not self._result and self._cancelled is None:
            self._start()
        self._update_text()
